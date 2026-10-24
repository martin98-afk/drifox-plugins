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

import os
import shutil
import threading

from loguru import logger

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

_PLUGIN = "magpie"
_DEFAULT_WEB_PORT = 3430

_PROFILE_NAME = "magpie-web"


def _caps(cap_id: str):
    """取某能力（独立弹窗无 ctx，统一走 sdk 的 caps_for，host 由宿主解析）。

    抽成模块级函数而非在各处内联 import：无 ctx 场景下 host 解析只有这一条
    路径，内联会让「拿不到能力」的兜底散落多处；也便于测试替换。
    """
    from app.plugins.sdk import caps_for

    return caps_for(cap_id, plugin=_PLUGIN, surface="ui")


def _magpie_installed() -> bool:
    """magpie 可执行文件是否在 PATH 上（决定引导文案走「启动」还是「安装」）。"""
    return shutil.which("magpie") is not None


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

    from PySide6.QtWebEngineCore import QWebEngineProfile

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

    _probe_done = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._provider = None
        self._colors: dict = {}
        self._loaded_once = False
        # 引导面板当前展示的分支：""=未连接 / "load_failed"=被拒绝
        # （主题刷新时要按同一分支重渲染，否则文案被冲回「未连接」版）
        self._guide_state = ""
        # _show_guide 存下的 cfg 快照（主题刷新按它重渲染，不重读配置）
        self._guide_cfg: dict = None

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
        self._guide = QWidget(self)
        guide_lay = QVBoxLayout(self._guide)
        guide_lay.setContentsMargins(24, 12, 24, 12)
        guide_lay.setSpacing(12)
        guide_lay.addStretch(1)

        self._guide_text = QLabel(self._guide)
        self._guide_text.setAlignment(Qt.AlignCenter)
        self._guide_text.setTextFormat(Qt.RichText)
        self._guide_text.setWordWrap(True)
        self._guide_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._guide_text.setText(self._guide_html("", ""))
        guide_lay.addWidget(self._guide_text)

        self._guide_btns = QWidget(self._guide)
        btn_lay = QHBoxLayout(self._guide_btns)
        btn_lay.setContentsMargins(0, 0, 0, 0)
        btn_lay.setSpacing(10)
        btn_lay.addStretch(1)

        self._copy_btn = PushButton("复制启动命令", self._guide_btns)
        self._copy_btn.clicked.connect(self._copy_command)
        btn_lay.addWidget(self._copy_btn)

        self._ask_btn = PushButton("让 AI 帮我装", self._guide_btns)
        self._ask_btn.clicked.connect(self._ask_ai_to_install)
        btn_lay.addWidget(self._ask_btn)

        btn_lay.addStretch(1)
        guide_lay.addWidget(self._guide_btns)
        guide_lay.addStretch(1)
        root.addWidget(self._guide, 1)

        self._view = None
        self._page = None
        try:
            from PySide6.QtWebEngineCore import QWebEnginePage
            from PySide6.QtWebEngineWidgets import QWebEngineView

            self._view = QWebEngineView(self)
            # profile 经 QWebEnginePage 注入再 setPage（PyQt5 无 setProfile 时的唯一路径，
            # PySide6 沿用同一结构）。page 必须由 Python 侧持有引用，否则被回收后
            # webview 变空白。
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
        self._guide_state = "load_failed" if load_failed else ""
        self._guide_cfg = dict(cfg or {})
        installed = _magpie_installed()
        self._guide_text.setText(
            self._guide_html(_start_command(cfg["port"]), cfg["key"], load_failed, installed)
        )
        # 未装 magpie 时「复制启动命令」没有意义，只留「让 AI 帮我装」
        self._copy_btn.setVisible(installed and not load_failed)
        self._apply_theme()

    def _open_in_browser(self):
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl(self._target_url()))

    def _copy_command(self):
        cmd = _start_command(_read_config()["port"])
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(cmd)
        self._notify("已复制", cmd)

    def _ask_ai_to_install(self):
        """把安装/启动指令写进输入框，交给对话里的模型去执行。

        用 input.write 而非自己 subprocess：装软件涉及下载、PATH、权限与平台
        差异，交给模型按当前环境处理比插件硬编码更稳；插件只负责把意图摆到
        用户眼前。
        """
        write = _caps("input.write")

        if write is None:
            self._notify("无法写入输入框", "当前宿主未提供 input.write 能力，请手动安装 magpie")
            return

        prompt = (
            "请帮我安装 magpie（https://github.com/yetone/magpie），安装好后启动它的网页服务，"
            "让 127.0.0.1:3430 能访问，然后告诉我一声。当前平台是 "
            f"{'Windows' if os.name == 'nt' else 'macOS/Linux'}。"
        )
        try:
            write(prompt, append=False, focus=True)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[magpie] 写入输入框失败: {e}")
            self._notify("写入失败", str(e))
            return
        self._notify("已填入输入框", "发送后模型会按你的环境装 magpie（可能需要下载与权限确认）")

    def _notify(self, title: str, content: str):
        """提示优先走 ui.notify 能力，拿不到就只记日志（弹窗内无 InfoBar parent）。"""
        notify = _caps("ui.notify")
        if notify is not None:
            try:
                notify(title, content)
                return
            except Exception as e:  # noqa: BLE001
                logger.debug(f"[magpie] notify 失败: {e}")
        logger.info(f"[magpie] {title}: {content}")

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
        self._guide_text.setStyleSheet(f"color: {c['text_secondary']};")
        # 用 isHidden() 而非 isVisible()：窗口尚未显示时父级不可见会让
        # isVisible() 恒为 False，导致主题切换时引导文案不重刷
        # 引导文案按 _show_guide 存下的 cfg 重渲染（不重新读配置：读到的端口
        # 可能已变，会把刚展示的分支文案冲成另一个端口的版本）
        if not self._guide.isHidden() and self._guide_cfg is not None:
            self._guide_text.setText(
                self._guide_html(
                    _start_command(self._guide_cfg["port"]),
                    self._guide_cfg["key"],
                    self._guide_state == "load_failed",
                    _magpie_installed(),
                )
            )

    # ── 文案 ─────────────────────────────────────────────

    def _guide_html(self, command: str, key: str, load_failed: bool = False, installed: bool = True) -> str:
        c = self._colors or self._ctx_colors()
        body_lines = []
        if load_failed:
            head = "magpie 拒绝了这次访问"
            body_lines.append(
                "magpie web 每次启动会换一个随机 key。固定它的办法：先设好环境变量"
                " <code>MAGPIE_WEB_KEY</code> 再启动，然后把同一个值填进插件设置里的"
                "「Web Key」。"
            )
        elif installed:
            head = "magpie 网页服务没有在监听"
            body_lines.append(
                "magpie 已安装。桌面 App 不对外开网页端口，需要在终端启动网页服务，"
                "然后点「重新加载」："
            )
            body_lines.append(
                "<code style=\"padding:2px 6px;border-radius:4px;"
                f"border:1px solid {c['border']}\">{command}</code>"
            )
            if not key:
                body_lines.append(
                    "另外：可以设 <code>MAGPIE_WEB_KEY</code> 固定 key，并填进插件设置。"
                )
        else:
            head = "没有找到 magpie"
            body_lines.append(
                "PATH 上没有 <code>magpie</code> 可执行文件。点下面的按钮把安装指令"
                "填进输入框，让对话里的模型按你的环境装（Windows / macOS / Linux 装法不同）。"
            )
            body_lines.append(
                '也可以自己去 <a href="https://usemagpie.ai">usemagpie.ai</a> 下载。'
            )
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
