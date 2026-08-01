# -*- coding: utf-8 -*-
"""浏览器控制端点 — 主进程内本地 HTTP 服务，供 MCP 服务器控制插件浏览器

架构：
    AI 模型 → MCP 服务器(子进程) → HTTP → 本模块(主进程) → 操作 QWebEngineView

要点：
- ThreadingHTTPServer 绑定 127.0.0.1:0（动态端口），随机 token 鉴权
- 端口/token/可用 python 路径写入 ../mcp/bridge.json，供 MCP 服务器连接
- 所有 Qt 操作经 _MainThreadDispatcher 派发到主线程执行（线程安全）
- 幂等启动：热重载时复用已启动的服务器

端点（POST /api/*，均需带 token）：
- status           服务器与浏览器状态
- navigate         导航到 URL（浏览器未开时自动打开）
- read             读取当前页文本/HTML
- execute_js       执行任意 JS（点击/输入/滚动/读取状态）
- screenshot       截图当前页 → base64 PNG
- back/forward/reload  导航控制
- tabs / switch_tab / new_tab / close_tab  标签管理
"""

import base64
import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from loguru import logger

# 复用 external_open 的主线程派发器（install_redirect 时已在主线程创建）
from .external_open import _get_dispatcher

_BRIDGE_FILE = None  # 插件根/mcp/bridge.json（由插件根路径确定）
_server_ref = {"server": None, "token": "", "port": 0}


# ── Qt 操作同步化（在主线程内用 QEventLoop 等异步回调）──

def _run_js_sync(view, js: str, timeout: float = 8.0) -> Any:
    """在主线程内同步执行 JS 并返回结果（QEventLoop 等待回调）"""
    from PyQt5.QtCore import QEventLoop, QTimer

    result = {"value": None, "done": False}
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)

    def _cb(value):
        result["value"] = value
        result["done"] = True
        loop.quit()

    view.page().runJavaScript(js, _cb)
    timer.start(int(timeout * 1000))
    loop.exec_()
    timer.stop()
    return result.get("value")


def _to_html_sync(view, timeout: float = 8.0) -> str:
    """主线程内同步获取页面 HTML"""
    from PyQt5.QtCore import QEventLoop, QTimer

    result = {"value": "", "done": False}
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)

    def _cb(value):
        result["value"] = value or ""
        result["done"] = True
        loop.quit()

    view.page().toHtml(_cb)
    timer.start(int(timeout * 1000))
    loop.exec_()
    timer.stop()
    return result.get("value") or ""


def _wait_load(view, timeout: float = 15.0) -> bool:
    """等待页面加载完成（loadFinished 同步化）"""
    from PyQt5.QtCore import QEventLoop, QTimer

    result = {"ok": False}
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    view.loadFinished.connect(lambda ok: (result.update(ok=bool(ok)), loop.quit()))
    timer.start(int(timeout * 1000))
    loop.exec_()
    timer.stop()
    return result["ok"]


# ── 浏览器操作（均在主线程执行）──

def _ensure_browser():
    """确保浏览器卡片存在并可见，返回 (card, view)；不可用返回 (None, None)"""
    from .browser_window import _get_current_card

    card = _get_current_card()
    if card is not None:
        return card, card._current_view()
    # 浏览器未打开 → 尝试自动打开浮动卡片
    try:
        from app.core.ui_plugin_registry import UIPluginRegistry
        from app.widgets.cards.card_manager import CardManager

        registry = UIPluginRegistry.get_instance()
        if "browser" in getattr(registry, "_floating_cards", {}):
            cm = CardManager.get_instance()
            visible = any(cm.is_card_visible("browser", wid) for wid in cm.get_all_windows())
            if not visible:
                registry.toggle_floating_card("browser")
            card = _get_current_card()
            if card is not None:
                return card, card._current_view()
    except Exception:
        pass
    return None, None


def _current_view():
    """获取当前活动视图（浏览器未开时尝试自动打开）"""
    return _ensure_browser()[1]


def _op_navigate(url: str, wait: bool = True) -> dict:
    card, view = _ensure_browser()
    if card is None or view is None:
        return {"ok": False, "error": "浏览器未打开且无法自动打开"}
    from .url_bar import normalize_url

    target = normalize_url(url) or url
    view.setUrl(_to_qurl(target))
    if wait:
        _wait_load(view)
    return {"ok": True, "url": view.url().toString(), "title": view.title()}


def _op_read(mode: str = "text") -> dict:
    view = _current_view()
    if view is None:
        return {"ok": False, "error": "浏览器未打开"}
    url = view.url().toString()
    title = view.title()
    if mode == "html":
        content = _to_html_sync(view)
    else:
        js = (
            "(function(){"
            "var b=document.body;if(!b)return '';"
            "var t=b.innerText||b.textContent||'';"
            "return t.replace(/\\n{3,}/g,'\\n\\n').slice(0,200000);"
            "})();"
        )
        content = _run_js_sync(view, js) or ""
    return {"ok": True, "url": url, "title": title, "content": content}


def _op_execute_js(js: str) -> dict:
    view = _current_view()
    if view is None:
        return {"ok": False, "error": "浏览器未打开"}
    value = _run_js_sync(view, js)
    return {"ok": True, "result": value}


def _op_screenshot() -> dict:
    view = _current_view()
    if view is None:
        return {"ok": False, "error": "浏览器未打开"}
    pixmap = view.grab()
    if pixmap.isNull():
        return {"ok": False, "error": "截图失败"}
    from PyQt5.QtCore import QBuffer, QByteArray, QIODevice

    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    pixmap.save(buf, "PNG")
    buf.close()
    return {"ok": True, "image": base64.b64encode(bytes(ba.data())).decode("ascii")}


def _op_back() -> dict:
    view = _current_view()
    if view is None:
        return {"ok": False, "error": "浏览器未打开"}
    if view.history().canGoBack():
        view.back()
        _wait_load(view)
    return {"ok": True, "url": view.url().toString()}


def _op_forward() -> dict:
    view = _current_view()
    if view is None:
        return {"ok": False, "error": "浏览器未打开"}
    if view.history().canGoForward():
        view.forward()
        _wait_load(view)
    return {"ok": True, "url": view.url().toString()}


def _op_reload() -> dict:
    view = _current_view()
    if view is None:
        return {"ok": False, "error": "浏览器未打开"}
    view.reload()
    _wait_load(view)
    return {"ok": True}


def _op_tabs() -> dict:
    from .browser_window import _get_current_card

    card = _get_current_card()
    if card is None:
        return {"ok": False, "error": "浏览器未打开"}
    tabs = []
    for i, entry in enumerate(card._views):
        tabs.append({
            "index": i,
            "title": entry.get("title", ""),
            "url": entry.get("url", ""),
            "active": i == card._tab_bar.currentIndex(),
        })
    return {"ok": True, "tabs": tabs, "active": card._tab_bar.currentIndex()}


def _op_switch_tab(index: int) -> dict:
    from .browser_window import _get_current_card

    card = _get_current_card()
    if card is None:
        return {"ok": False, "error": "浏览器未打开"}
    if not (0 <= index < len(card._views)):
        return {"ok": False, "error": f"标签索引越界: {index}"}
    card._tab_bar.setCurrentIndex(index)
    return {"ok": True, "index": index}


def _op_new_tab(url: str = "") -> dict:
    from .browser_window import _get_current_card

    card = _get_current_card()
    if card is None:
        return {"ok": False, "error": "浏览器未打开"}
    idx = card._new_tab(url)
    return {"ok": True, "index": idx}


def _op_close_tab(index: int) -> dict:
    from .browser_window import _get_current_card

    card = _get_current_card()
    if card is None:
        return {"ok": False, "error": "浏览器未打开"}
    if not (0 <= index < len(card._views)):
        return {"ok": False, "error": f"标签索引越界: {index}"}
    card._close_tab(index)
    return {"ok": True}


def _to_qurl(url: str):
    from PyQt5.QtCore import QUrl

    return QUrl(url)


# ── HTTP 请求处理 ──

_OP_HANDLERS = {
    "navigate": lambda args: _dispatch_qt(lambda: _op_navigate(args.get("url", ""))),
    "read": lambda args: _dispatch_qt(lambda: _op_read(args.get("mode", "text"))),
    "execute_js": lambda args: _dispatch_qt(lambda: _op_execute_js(args.get("js", ""))),
    "screenshot": lambda args: _dispatch_qt(_op_screenshot),
    "back": lambda args: _dispatch_qt(_op_back),
    "forward": lambda args: _dispatch_qt(_op_forward),
    "reload": lambda args: _dispatch_qt(_op_reload),
    "tabs": lambda args: _dispatch_qt(_op_tabs),
    "switch_tab": lambda args: _dispatch_qt(lambda: _op_switch_tab(int(args.get("index", 0)))),
    "new_tab": lambda args: _dispatch_qt(lambda: _op_new_tab(args.get("url", ""))),
    "close_tab": lambda args: _dispatch_qt(lambda: _op_close_tab(int(args.get("index", 0)))),
}


def _dispatch_qt(fn, timeout: float = 20.0):
    """派发 Qt 操作到主线程执行并同步等待结果（当前即主线程则直接执行）"""
    dispatcher = _get_dispatcher()
    if dispatcher is None:
        # 派发器未就绪时，仅主线程可直接执行；非主线程禁止跨线程 UI 操作
        try:
            from PyQt5.QtCore import QThread
            from PyQt5.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None and QThread.currentThread() != app.thread():
                return {"ok": False, "error": "主线程派发器未就绪"}
        except Exception:
            pass
        return fn()
    event = threading.Event()
    result = {"value": None, "done": False}

    def _do():
        try:
            result["value"] = fn()
        except Exception as e:
            result["value"] = {"ok": False, "error": f"操作异常: {e}"}
        finally:
            result["done"] = True
            event.set()

    dispatcher.call(_do)
    event.wait(timeout)
    if not result["done"]:
        return {"ok": False, "error": "主线程响应超时"}
    return result["value"]


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 静默访问日志
        pass

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            path = urlparse(self.path).path
            if path == "/api/status":
                data = {"ok": True, "browser": _op_tabs()["ok"]}
                self._send_json(data)
                return
            if body.get("token") != _server_ref["token"]:
                self._send_json({"ok": False, "error": "token 无效"}, 401)
                return
            op = path.rsplit("/", 1)[-1]
            handler = _OP_HANDLERS.get(op)
            if handler is None:
                self._send_json({"ok": False, "error": f"未知操作: {op}"}, 404)
                return
            self._send_json(handler(body))
        except Exception as e:
            logger.exception("[browser-control] 请求处理异常")
            self._send_json({"ok": False, "error": str(e)}, 500)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/healthz":
            self._send_json({"ok": True})
            return
        self._send_json({"ok": False, "error": "not found"}, 404)

    def _send_json(self, data: dict, code: int = 200):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _find_python() -> str:
    """寻找能 import mcp 的 python 解释器（供 MCP 服务器自引导），找不到返回空串"""
    import shutil
    import subprocess
    import sys as _sys

    candidates = []
    # 1. 当前解释器（仅当确实是 python，而非打包 exe）
    exe = _sys.executable
    if exe and os.path.basename(exe).lower().startswith("python"):
        candidates.append(exe)
    # 2. 开发环境 venv（源码运行 / 常见位置）
    for p in (
        Path(exe).parent.parent / ".venv" / "Scripts" / "python.exe",
        Path(r"D:\work\DriFox\.venv\Scripts\python.exe"),
        Path.home() / "work" / "DriFox" / ".venv" / "Scripts" / "python.exe",
    ):
        if p.exists():
            candidates.append(str(p))
    # 3. PATH 中的 python
    for name in ("python", "python3", "py"):
        p = shutil.which(name)
        if p and p not in candidates:
            candidates.append(p)
    # 验证候选能 import mcp（不能则跳过，绝不选非 python 可执行文件）
    for c in candidates:
        try:
            r = subprocess.run(
                [c, "-c", "import mcp, httpx"], capture_output=True, timeout=10
            )
            if r.returncode == 0:
                return c
        except Exception:
            continue
    return ""


def _write_bridge(plugin_root, port: int, token: str):
    """写桥接信息：端口/token/可用的 python，供 MCP 服务器读取"""
    global _BRIDGE_FILE
    mcp_dir = plugin_root / "mcp"
    mcp_dir.mkdir(parents=True, exist_ok=True)
    _BRIDGE_FILE = mcp_dir / "bridge.json"

    data = {
        "port": port,
        "token": token,
        "python_executable": _find_python(),
        "plugin_root": str(plugin_root),
    }
    try:
        _BRIDGE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[browser-control] 写入 bridge.json 失败: {e}")


def start_control_server(plugin_root) -> Optional[ThreadingHTTPServer]:
    """启动浏览器控制 HTTP 服务器（幂等）。plugin_root: 插件根目录 Path"""
    existing = _server_ref.get("server")
    if existing is not None:
        return existing
    try:
        token = secrets.token_hex(16)
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        port = server.server_address[1]
        _server_ref.update(server=server, token=token, port=port)
        _write_bridge(plugin_root, port, token)
        t = threading.Thread(target=server.serve_forever, daemon=True, name="browser-control-http")
        t.start()
        logger.info(f"[browser-control] 控制端点已启动: 127.0.0.1:{port} (token={'*' * 4}{token[-4:]})")
        return server
    except Exception:
        logger.exception("[browser-control] 控制端点启动失败")
        return None
