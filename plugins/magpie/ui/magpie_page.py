# -*- coding: utf-8 -*-
"""magpie 网页界面内容页（内嵌 magpie web）。

数据源：magpie 的网页服务（默认 127.0.0.1:3430），不是网关 3425——那两个是
不同进程入口，网页服务只在 ``magpie web`` / ``magpie serve --web`` /
``magpie daemon install --web`` 时存在。

页面三态：
- 探测中：显示「正在连接…」
- 不可达：显示命令指引（该跑哪条命令才能开这个端口）
- 已连上：QWebEngineView 加载，顶部状态条保留「重新加载 / 在浏览器打开」

key：magpie web 每次启动会换一个随机 key，URL 必须带 ``?k=<key>``。要固定就在
启动前设 ``MAGPIE_WEB_KEY``，再把同一个值填进插件设置。key 留空时仍尝试加载，
失败由 magpie 自己的页面提示。
"""

import threading

from loguru import logger

from PyQt5.QtCore import QUrl, Qt, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

_PLUGIN = "magpie"
_DEFAULT_WEB_PORT = 3430

_PROFILE_NAME = "magpie-web"


def _read_config() -> dict:
    """读插件设置（端口 / key）。配置系统不可用时回默认值。"""
    try:
        from app.plugins.managers.plugin_config_store import PluginConfigStore

        store = PluginConfigStore()
        port = store.get(_PLUGIN, "web_port")
        return {
            "port": int(port) if str(port or "").strip().isdigit() else _DEFAULT_WEB_PORT,
            "key": str(store.get(_PLUGIN, "web_key") or "").strip(),
        }
    except Exception as e:  # noqa: BLE001 — 配置不可用走默认值
        logger.warning(f"[magpie] 读取 web 配置失败，按默认: {e}")
        return {"port": _DEFAULT_WEB_PORT, "key": ""}


_web_profile = None


def _get_web_profile():
    """独立命名的持久 Profile（延迟创建）。

    不复用主程序共享 profile：那是消息卡片在用，Cookie/缓存混用会互相污染；
    也不用默认 profile（改它的策略会影响整个应用）。
    """
    global _web_profile
    if _web_profile is not None:
        try:
            _web_profile.storageName()
            return _web_profile
        except RuntimeError:
            _web_profile = None

    from PyQt5.QtWebEngineWidgets import QWebEngineProfile

    profile = QWebEngineProfile(_PROFILE_NAME)
    profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
    profile.setHttpCacheType(QWebEngineProfile.DiskHttpCache)
    profile.setHttpCacheMaximumSize(64 * 1024 * 1024)
    _web_profile = profile
    return profile


def _probe(port: int, timeout: float = 2.0) -> bool:
    """探测网页服务是否在监听（任意 HTTP 响应都算活着，401/403 也是活着）。"""
    import urllib.error
    import urllib.request

    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


class MagpieWebPage(QWidget):
    """magpie 网页界面（独立弹窗内容页）。"""

    _probe_done = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._provider = None
        self._colors: dict = {}
        self._loaded_once = False

        self._build_ui()
        self._probe_done.connect(self._on_probe_done)

    # ── 三约定接口 ────────────────────────────────────────

    def set_context_provider(self, provider):
        self._provider = provider

    def show_card(self):
        """弹窗打开/激活入口：取色 + 探测 + 加载。"""
        self._apply_theme()
        self._connect_and_load()

    def refresh_theme(self):
        self._apply_theme()

    # ── 骨架 ─────────────────────────────────────────────

    def _build_ui(self):
        from qfluentwidgets import PushButton

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QWidget(self)
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(14, 8, 14, 8)
        bar_lay.setSpacing(10)

        self._status = QLabel("正在连接…", bar)
        bar_lay.addWidget(self._status, 1)

        self._reload_btn = PushButton("重新加载", bar)
        self._reload_btn.clicked.connect(self._connect_and_load)
        bar_lay.addWidget(self._reload_btn)

        self._browser_btn = PushButton("在浏览器打开", bar)
        self._browser_btn.clicked.connect(self._open_in_browser)
        bar_lay.addWidget(self._browser_btn)

        root.addWidget(bar)

        # 不可达时的指引面板（与 webview 互斥显示）
        self._guide = QLabel(self)
        self._guide.setAlignment(Qt.AlignCenter)
        self._guide.setTextFormat(Qt.RichText)
        self._guide.setWordWrap(True)
        self._guide.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._guide.setText(self._guide_html("", ""))
        root.addWidget(self._guide, 1)

        self._view = None
        self._page = None
        try:
            from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineView

            self._view = QWebEngineView(self)
            # PyQt5 的 QWebEngineView 没有 setProfile：profile 只能经 QWebEnginePage
            # 注入。page 必须由 Python 侧持有引用，否则被回收后 webview 变空白。
            self._page = QWebEnginePage(_get_web_profile(), self._view)
            self._view.setPage(self._page)
            self._view.loadFinished.connect(self._on_load_finished)
            self._view.setVisible(False)
            root.addWidget(self._view, 1)
        except Exception as e:  # noqa: BLE001 — 缺 QtWebEngine 时降级
            logger.warning(f"[magpie] QWebEngineView 不可用，降级为指引面板: {e}")
            self._view = None
            self._browser_btn.setEnabled(False)

    # ── 连接与状态 ───────────────────────────────────────

    def _target_url(self) -> str:
        cfg = _read_config()
        url = f"http://127.0.0.1:{cfg['port']}/"
        if cfg["key"]:
            url += f"?k={cfg['key']}"
        return url

    def _connect_and_load(self):
        cfg = _read_config()
        self._status.setText(f"正在连接 127.0.0.1:{cfg['port']} …")
        self._reload_btn.setEnabled(False)

        def work():
            ok = _probe(cfg["port"])
            try:
                self._probe_done.emit(ok)
            except RuntimeError:
                pass  # 页面已销毁（窗口关闭）

        threading.Thread(target=work, daemon=True, name="magpie-web-probe").start()

    def _on_probe_done(self, ok: bool):
        self._reload_btn.setEnabled(True)
        cfg = _read_config()
        if not ok:
            self._status.setText("未连接")
            self._show_guide(cfg)
            return

        self._guide.setVisible(False)
        if self._view is None:
            self._status.setText("已连接（缺 QtWebEngine，无法内嵌）")
            return

        self._view.setVisible(True)
        self._status.setText(f"已连接 127.0.0.1:{cfg['port']}")
        self._view.setUrl(QUrl(self._target_url()))
        self._loaded_once = True

    def _on_load_finished(self, ok: bool):
        if ok:
            return
        # 服务在监听但页面拒绝访问：几乎总是 key 不对
        self._status.setText("页面加载失败（多为 web key 不匹配）")
        self._show_guide(_read_config(), load_failed=True)

    def _show_guide(self, cfg: dict, load_failed: bool = False):
        if self._view is not None:
            self._view.setVisible(False)
        self._guide.setVisible(True)
        self._guide.setText(self._guide_html(_start_command(cfg["port"]), cfg["key"], load_failed))
        self._apply_theme()

    def _open_in_browser(self):
        from PyQt5.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl(self._target_url()))

    # ── 主题 ─────────────────────────────────────────────

    def _ctx_colors(self) -> dict:
        from qfluentwidgets import isDarkTheme

        ctx = self._provider() if callable(self._provider) else {}
        colors = (ctx or {}).get("colors", {}) or {}
        dark = isDarkTheme()
        return {
            "text_primary": colors.get("text_primary")
            or ("rgba(255,255,255,0.9)" if dark else "rgba(0,0,0,0.85)"),
            "text_secondary": colors.get("text_secondary")
            or ("rgba(255,255,255,0.55)" if dark else "rgba(0,0,0,0.45)"),
            "border": colors.get("border") or ("rgba(255,255,255,0.12)" if dark else "rgba(0,0,0,0.12)"),
        }

    def _apply_theme(self):
        self._colors = self._ctx_colors()
        c = self._colors
        self._status.setStyleSheet(f"color: {c['text_primary']};")
        self._guide.setStyleSheet(f"color: {c['text_secondary']};")
        # 用 isHidden() 而非 isVisible()：窗口尚未显示时父级不可见会让
        # isVisible() 恒为 False，导致主题切换时引导文案不重刷
        if not self._guide.isHidden():
            cfg = _read_config()
            self._guide.setText(self._guide_html(_start_command(cfg["port"]), cfg["key"]))

    # ── 文案 ─────────────────────────────────────────────

    def _guide_html(self, command: str, key: str, load_failed: bool = False) -> str:
        c = self._colors or self._ctx_colors()
        head = "magpie 的网页界面没有在监听" if not load_failed else "magpie 拒绝了这次访问"
        body_lines = []
        if not load_failed:
            body_lines.append("在终端运行其中任一条，开启网页服务后点「重新加载」：")
            body_lines.append(
                "<code style=\"padding:2px 6px;border-radius:4px;"
                f"border:1px solid {c['border']}\">{command}</code>"
            )
        else:
            body_lines.append(
                "magpie web 每次启动会换一个随机 key。固定它的办法：先设好环境变量"
                " <code>MAGPIE_WEB_KEY</code> 再启动，然后把同一个值填进插件设置里的"
                "「Web Key」。"
            )
        if not key and not load_failed:
            body_lines.append("另外：可以设 <code>MAGPIE_WEB_KEY</code> 固定 key，并填进插件设置。")
        body = "<br><br>".join(body_lines)
        return (
            f"<div style=\"font-size:15px;color:{c['text_primary']};margin-bottom:8px\">{head}</div>"
            f"<div>{body}</div>"
        )


def _start_command(port: int) -> str:
    """按端口给出可复制的启动命令（3430 是默认端口，其他端口需显式 --addr）。"""
    if port == _DEFAULT_WEB_PORT:
        return "magpie web --no-open"
    return f"magpie web --addr 127.0.0.1:{port} --no-open"
