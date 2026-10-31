# -*- coding: utf-8 -*-
"""B站能力控制端点（宿主进程内）— mcp/server.py 的 HTTP 后端。

browser 插件同款两段式：MCP stdio 子进程只做转发，重依赖（vendor /
bilibili_api / deps / stdlib 与 PIL 仲裁 / 凭证 env）全留宿主进程。
端口/token 写 mcp/bridge.json，MCP 壳自引导解释器后按 bridge 连入。

本模块放 ui/ 包内（非 biliscroll_core/）：ui 热重载会清
ui_plugin_bili_scroll.* 的 sys.modules 强制重编，端点路由改动才能即时生效；
biliscroll_core.* 是共享顶层名模块会滞留旧版。

接口：
    GET  /healthz                      存活探针（无鉴权）
    GET  /api/tools?token=...          工具表（name/description/inputSchema）
    POST /api/tools {token}            同上（MCP 壳统一 POST 形态）
    POST /api/call {token,name,kwargs} 执行工具 → {ok, content|error}
"""
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from loguru import logger

import importlib

from biliscroll_core import bili_impl

# biliscroll_core.* 热重载滞留旧版（含 patch ⑨ 登录补丁）；
# bili_impl 顶层仲裁/patch 全幂等，reload 自愈保证补丁与磁盘一致
importlib.reload(bili_impl)

_BRIDGE_FILE = None  # 插件根/mcp/bridge.json
_server_ref = {"server": None, "token": "", "port": 0}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 静默访问日志
        pass

    def do_GET(self):
        try:
            path = urlparse(self.path).path
            if path == "/healthz":
                self._send_json({"ok": True})
                return
            if path == "/api/tools":
                if self._auth_failed():
                    return
                tools = [
                    {
                        "name": name,
                        "description": schema["function"]["description"],
                        "inputSchema": schema["function"]["parameters"],
                    }
                    for name, schema in sorted(bili_impl.SCHEMAS.items())
                ]
                self._send_json({"ok": True, "tools": tools})
                return
            self._send_json({"ok": False, "error": "not found"}, 404)
        except Exception as e:
            logger.exception("[bili-control] GET 处理异常")
            self._send_json({"ok": False, "error": str(e)}, 500)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            path = urlparse(self.path).path
            if path == "/api/tools":
                # MCP 壳的 _api 统一走 POST；工具表也提供 POST 形态
                if body.get("token") != _server_ref["token"]:
                    self._send_json({"ok": False, "error": "token 无效"}, 401)
                    return
                tools = [
                    {
                        "name": name,
                        "description": schema["function"]["description"],
                        "inputSchema": schema["function"]["parameters"],
                    }
                    for name, schema in sorted(bili_impl.SCHEMAS.items())
                ]
                self._send_json({"ok": True, "tools": tools})
                return
            if path != "/api/call":
                self._send_json({"ok": False, "error": "not found"}, 404)
                return
            if body.get("token") != _server_ref["token"]:
                self._send_json({"ok": False, "error": "token 无效"}, 401)
                return
            name = body.get("name") or ""
            impl = bili_impl.IMPLS.get(name)
            if impl is None:
                self._send_json({"ok": False, "error": f"未知工具: {name}"}, 404)
                return
            kwargs = body.get("kwargs") or {}
            content = impl(**kwargs)
            self._maybe_qrcode_popup(name, content)
            self._send_json({"ok": True, "content": content})
        except Exception as e:
            # 上游网络错/B站风控等属常态，WARNING 即可；错误文本回给模型自行改写重试
            logger.warning(f"[bili-control] 工具调用失败: {type(e).__name__}: {e}")
            self._send_json({"ok": False, "error": f"{type(e).__name__}: {e}"})

    def _maybe_qrcode_popup(self, name: str, content: str):
        """扫码体验：bili_login 出码弹窗直显；登录 done/timeout 自动收窗。"""
        try:
            from .qrcode_popup import close_qrcode, show_qrcode

            if name == "bili_login":
                data = json.loads(content)
                if data.get("status") == "qrcode_ready":
                    img = data.get("qrcode_image") or ""
                    if img.startswith("data:image"):
                        show_qrcode(img)
            elif name == "bili_login_check" and isinstance(content, str):
                if '"status": "done"' in content or '"status": "timeout"' in content:
                    close_qrcode()
        except Exception as e:
            logger.warning(f"[bili-control] 二维码弹窗处理失败: {e}")

    def _auth_failed(self) -> bool:
        qs = parse_qs(urlparse(self.path).query)
        if (qs.get("token") or [""])[0] != _server_ref["token"]:
            self._send_json({"ok": False, "error": "token 无效"}, 401)
            return True
        return False

    def _send_json(self, data, code=200):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _find_python() -> str:
    """寻找能 import mcp+httpx 的解释器（供 MCP 壳自引导），找不到返回空串。"""
    import os as _os
    import shutil
    import subprocess
    import sys as _sys

    kwargs = {}
    if _os.name == "nt":
        flag = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if flag:
            kwargs["creationflags"] = flag

    candidates = []
    exe = _sys.executable
    # 打包宿主的解释器是冻结 exe，不能拉子进程；仅源码 python 可候选
    if exe and _os.path.basename(exe).lower().startswith("python"):
        candidates.append(exe)
    for p in (
        Path(exe).parent.parent / ".venv" / "Scripts" / "python.exe",
        Path(r"D:\work\DriFox\.venv\Scripts\python.exe"),
        Path.home() / "work" / "DriFox" / ".venv" / "Scripts" / "python.exe",
    ):
        if p.exists():
            candidates.append(str(p))
    for name in ("python", "python3", "py"):
        p = shutil.which(name)
        if p and p not in candidates:
            candidates.append(p)
    for c in candidates:
        try:
            r = subprocess.run(
                [c, "-c", "import mcp, httpx"],
                capture_output=True,
                timeout=10,
                **kwargs,
            )
            if r.returncode == 0:
                return c
        except Exception:
            continue
    return ""


def _resolve_python(plugin_root: Path) -> str:
    """bridge.json 里已有探测结果且解释器仍在 → 复用，避免启动期重复 spawn。"""
    try:
        bridge = plugin_root / "mcp" / "bridge.json"
        if bridge.exists():
            prev = json.loads(bridge.read_text(encoding="utf-8")).get("python_executable", "")
            if prev and Path(prev).exists():
                return prev
    except Exception:
        pass
    return _find_python()


def _write_bridge(plugin_root: Path, port: int, token: str):
    global _BRIDGE_FILE
    mcp_dir = plugin_root / "mcp"
    mcp_dir.mkdir(parents=True, exist_ok=True)
    _BRIDGE_FILE = mcp_dir / "bridge.json"
    data = {
        "port": port,
        "token": token,
        "python_executable": _resolve_python(plugin_root),
        "plugin_root": str(plugin_root),
    }
    try:
        _BRIDGE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[bili-control] 写入 bridge.json 失败: {e}")


def start_control_server(plugin_root) -> Optional[ThreadingHTTPServer]:
    """启动 B站控制端点（幂等）。plugin_root: 插件根目录 Path"""
    existing = _server_ref.get("server")
    if existing is not None:
        return existing
    try:
        token = secrets.token_hex(16)
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        port = server.server_address[1]
        _server_ref.update(server=server, token=token, port=port)
        _write_bridge(Path(plugin_root), port, token)
        t = threading.Thread(target=server.serve_forever, daemon=True, name="bili-control-http")
        t.start()
        logger.info(f"[bili-control] 控制端点已启动: 127.0.0.1:{port} (token={'*' * 4}{token[-4:]})")
        return server
    except Exception:
        logger.exception("[bili-control] 控制端点启动失败")
        return None


def stop_control_server():
    """停止端点（unload_ui/热重载回调；幂等）。"""
    server = _server_ref.get("server")
    if server is not None:
        try:
            server.shutdown()
            server.server_close()
        except Exception as e:
            logger.warning(f"[bili-control] 停止端点失败: {e}")
        _server_ref.clear()
        logger.info("[bili-control] 控制端点已停")
