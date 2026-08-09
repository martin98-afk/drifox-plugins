# -*- coding: utf-8 -*-
"""外部链接重定向 — 将主程序的 http/https 外链默认打开到 DriFox 内置浏览器

原理（monkey patch，UI 插件在主程序进程内执行）：
- patch ``webbrowser.open``：标准库模块函数，全局生效
  （OAuth 授权、API 文档、设置页外链等所有调用点）
- patch ``PyQt5.QtGui.QDesktopServices``：把模块属性替换为代理类。
  ⚠️ ``QDesktopServices.openUrl`` 是 sip 只读类属性，不能直接替换；
  但 ``PyQt5.QtGui`` 是普通模块、模块属性可写。
  message_card.py / update_checker.py 均为函数内延迟 import，
  patch 后拿到代理类；main_widget.py 顶层 import 的旧引用不受影响
  （本地文件打开本就走系统，且非 http 协议会放行）。
- patch ``TerminalTools.execute_bash``：拦截大模型通过 bash 执行的
  ``start <url>`` / ``cmd /c start <url>`` / ``explorer <url>``，
  同样转交内置浏览器（用户明确要求大模型 start 开网页也走插件浏览器）。

拦截行为（配置驱动，见 redirect_config.py）：
- 全局开关 enabled：总闸，关闭后一切放行
- intercept_system：拦截 webbrowser/QDesktopServices 的 http/https 外链
- intercept_shell：拦截 bash start/explorer <url>
- intercept_html：拦截本地 html 文件（file:// 或磁盘 .html 路径）→ 内置浏览器
  （修复原实现「打开 html 文件不拦截」的问题）
- 其余（file 非 html / mailto:/本地可执行文件等）→ 原系统逻辑
- 浏览器插件未注册 / 卡片不可用 → 回退系统浏览器

幂等：热重载时 register_ui 再次执行，通过标记检测避免重复嵌套 patch。
"""

import re
import webbrowser
from typing import Any, Optional

from loguru import logger
from PyQt5.QtCore import QObject, pyqtSignal

from .redirect_config import should_intercept, to_browser_url

# ── 幂等标记 ──────────────────────────────────────────────
_installed = False
_orig_webbrowser_open: Any = None
_orig_qdesktop_openurl: Any = None


class _MainThreadDispatcher(QObject):
    """跨线程派发器：信号 AutoConnection 自动投递到接收者（主线程）事件循环。

    ⚠️ QTimer.singleShot 的定时器依附于调用线程，在无事件循环的工作线程里
    永远不会触发；必须用信号投递到主线程，才能保证 UI 操作真正执行。
    """

    _requested = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._requested.connect(self._handle)

    def _handle(self, fn):
        try:
            fn()
        except Exception:
            logger.exception("[browser-redirect] 主线程派发任务异常")

    def call(self, fn):
        self._requested.emit(fn)


_dispatcher: Optional[_MainThreadDispatcher] = None


def _get_dispatcher() -> Optional[_MainThreadDispatcher]:
    """获取主线程派发器（须在主线程创建，否则返回 None 走直接调用）"""
    global _dispatcher
    if _dispatcher is None:
        try:
            from PyQt5.QtCore import QThread
            from PyQt5.QtWidgets import QApplication

            app = QApplication.instance()
            if app is None or QThread.currentThread() != app.thread():
                return None  # 不在主线程，不能安全创建
            _dispatcher = _MainThreadDispatcher()
        except Exception:
            return None
    return _dispatcher


def _is_http(url: str) -> bool:
    """仅拦截 http/https（scheme 大小写不敏感）

    注：真实拦截决策统一走 redirect_config.should_intercept（含 html 与
    各入口配置开关）；本函数仅保留给 bash URL 提取等无配置语义的内部判断。
    """
    u = url.strip().lower()
    return u.startswith("http://") or u.startswith("https://")


def _open_in_browser(url: str) -> bool:
    """尝试用内置浏览器打开链接：显示浏览器卡片 + 新开标签页导航

    浏览器不可用（插件未注册 / 卡片创建失败）返回 False，由调用方回退系统。
    """
    try:
        from app.core.ui_plugin_registry import UIPluginRegistry
        from app.widgets.cards.card_manager import CardManager
        from .browser_window import _get_current_card
        from .url_bar import normalize_url

        registry = UIPluginRegistry.get_instance()
        if "browser" not in getattr(registry, "_floating_cards", {}):
            logger.warning(f"[browser-redirect] browser 卡片未注册，回退系统浏览器: {url}")
            return False  # 浏览器插件未注册 → 回退系统浏览器

        target = normalize_url(url) or url

        # 确保浏览器卡片可见（已可见则不重复触发 toggle 关闭）
        cm = CardManager.get_instance()
        visible = any(cm.is_card_visible("browser", wid) for wid in cm.get_all_windows())
        logger.debug(f"[browser-redirect] 打开 {target}，浏览器当前可见={visible}")
        if not visible:
            registry.toggle_floating_card("browser")

        card = _get_current_card()
        if card is None:
            logger.warning(f"[browser-redirect] 浏览器卡片实例不可用，回退系统浏览器: {url}")
            return False
        card._new_tab(target)  # 总是新开标签页
        logger.info(f"[browser-redirect] 已在内置浏览器新标签打开: {target}")
        return True
    except Exception:
        logger.exception(f"[browser-redirect] 打开内置浏览器异常，回退系统浏览器: {url}")
        return False


def _open_in_browser_threadsafe(url: str, timeout: float = 8.0) -> bool:
    """线程安全入口：非 UI 线程调用时派发到主线程执行并同步等待结果

    返回真实结果：主线程成功打开 → True；失败 → False（调用方回退系统浏览器）。
    避免异步"假成功"（QTimer.singleShot 在工作线程永远不会触发）。
    """
    import threading

    try:
        from PyQt5.QtCore import QThread
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None and QThread.currentThread() != app.thread():
            dispatcher = _get_dispatcher()
            if dispatcher is None:
                # ⚠️ 绝不能直接调用：跨线程创建 QWidget 会导致 Qt 崩溃。
                # 派发器不可用（应只在插件安装前出现）→ 回退系统浏览器。
                logger.warning("[browser-redirect] 派发器不可用且当前非主线程，回退系统浏览器（避免跨线程 UI 崩溃）")
                return False
            event = threading.Event()
            result = {"ok": False}

            def _do():
                try:
                    result["ok"] = _open_in_browser(url)
                finally:
                    event.set()

            dispatcher.call(_do)
            event.wait(timeout)
            if not event.is_set():
                logger.warning(f"[browser-redirect] 主线程响应超时，回退系统浏览器: {url}")
            return result["ok"]
    except Exception:
        pass
    return _open_in_browser(url)


def _redirect_webbrowser_open(url, new=0, autoraise=True):
    """webbrowser.open 代理：按配置拦截 http/https + 本地 html → 内置浏览器"""
    if isinstance(url, str) and should_intercept(url, "system"):
        if _open_in_browser_threadsafe(to_browser_url(url)):
            return True
    return _orig_webbrowser_open(url, new, autoraise)


class _RedirectDesktopServices:
    """QDesktopServices 代理类：openUrl 按配置拦截到内置浏览器"""

    _drifox_redirect = True  # 幂等标记：热重载检测已 patch

    @staticmethod
    def openUrl(url) -> bool:
        try:
            url_str = url.toString() if hasattr(url, "toString") else str(url)
        except Exception:
            url_str = str(url)
        if should_intercept(url_str, "system"):
            if _open_in_browser_threadsafe(to_browser_url(url_str)):
                return True
        return _orig_qdesktop_openurl(url)


def install_redirect() -> bool:
    """安装外部链接重定向（register_ui 时调用）。返回是否完成注入。

    幂等：已注入过（含上次热重载遗留的代理）→ 直接返回，避免嵌套 patch。
    """
    global _installed, _orig_webbrowser_open, _orig_qdesktop_openurl

    # 已注入标记（本模块实例 / 热重载遗留代理）
    if _installed or getattr(webbrowser.open, "_drifox_redirect", False):
        # 热重载后本模块是新的，_dispatcher 为 None，需确保重建（register_ui 在主线程）
        _get_dispatcher()
        return True
    try:
        import PyQt5.QtGui as _qtgui
    except Exception:
        _qtgui = None
    if _qtgui is not None and getattr(_qtgui.QDesktopServices, "_drifox_redirect", False):
        return True

    # 1) patch webbrowser.open
    _orig_webbrowser_open = webbrowser.open
    _redirect_webbrowser_open._drifox_redirect = True  # type: ignore[attr-defined]
    webbrowser.open = _redirect_webbrowser_open  # type: ignore[assignment]

    # 2) patch PyQt5.QtGui.QDesktopServices（模块属性 → 代理类）
    if _qtgui is not None:
        _orig_qdesktop_openurl = _qtgui.QDesktopServices.openUrl
        _qtgui.QDesktopServices = _RedirectDesktopServices

    # 3) patch TerminalTools.execute_bash：拦截 start <url> 等命令
    bash_ok = install_bash_redirect()

    # 4) 预创建主线程派发器（register_ui 在主线程执行，必须在此创建，
    #    否则工作线程首次调用 _get_dispatcher 会因不在主线程而拒绝创建）
    _get_dispatcher()

    _installed = True
    logger.info(f"[browser-redirect] 外部链接重定向已安装 (bash拦截={'OK' if bash_ok else '跳过'}, 派发器={'OK' if _dispatcher is not None else '不可用'})")
    return True


# ── bash start 命令拦截（大模型用 bash 执行 start xxx 打开网页）── ──

_START_RE = re.compile(
    r"^\s*(?:cmd(?:\.exe)?\s*/c\s+)?(?P<cmd>start|explorer(?:\.exe)?)\b\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_START_OPT_WITH_ARG_RE = re.compile(r"^/(?:d|w)\s+\S+\s*", re.IGNORECASE)
_START_OPT_BARE_RE = re.compile(r"^/[a-z]+\s*", re.IGNORECASE)


def _strip_start_title(rest: str, is_start: bool) -> str:
    """start 命令第一个引号参数是窗口标题（可为空），剥掉它；explorer 无此语法"""
    if is_start and rest.startswith('"'):
        end = rest.find('"', 1)
        if end != -1:
            return rest[end + 1 :].strip()
    return rest


def _strip_start_options(rest: str) -> str:
    """剥掉 start 的选项（/d path、/w title、/min /max /b 等）"""
    while True:
        m = _START_OPT_WITH_ARG_RE.match(rest)
        if m:
            rest = rest[m.end() :]
            continue
        m = _START_OPT_BARE_RE.match(rest)
        if m:
            rest = rest[m.end() :]
            continue
        break
    return rest


def _extract_start_url(command: str) -> Optional[str]:
    """从 start / explorer 命令中提取 URL 或本地 html 文件路径，非目标返回 None

    支持形态：
    - start https://example.com
    - start "" https://example.com
    - start /min https://example.com
    - cmd /c start http://localhost:8080
    - explorer "https://example.com"
    - start D:\\report.html / explorer report.html  # 本地 html（走 intercept_html）
    非 URL 且非 html 文件（start notepad.exe / explorer D:\\folder）→ None，不拦截。
    """
    from .redirect_config import _is_local_html

    m = _START_RE.match(command.strip())
    if not m:
        return None
    is_start = m.group("cmd").lower().startswith("start")
    rest = m.group("rest").strip()
    rest = _strip_start_title(rest, is_start)
    rest = _strip_start_options(rest)
    tok = rest.split(None, 1)[0].strip().strip('"') if rest else ""
    if not tok:
        return None
    # 可执行/脚本文件不是 URL（notepad.exe / run.bat 等）。
    # 注意不含 .com：它是合法域名后缀（example.com）。
    if re.search(r"\.(?:exe|bat|cmd|msi|lnk|dll|ps1|vbs|jar)$", tok, re.IGNORECASE):
        return None
    # 本地 html 文件（D:/a.html、/tmp/a.html、file:///a.html）→ 直接返回
    if _is_local_html(tok):
        return tok
    # 规范化：localhost/裸域名补 scheme；非 URL（本地路径/可执行文件）→ 空
    try:
        from .url_bar import normalize_url
    except ImportError:
        try:
            from url_bar import normalize_url
        except Exception:
            normalize_url = None
    if normalize_url is not None:
        try:
            return normalize_url(tok) or None
        except Exception:
            return tok if _is_http(tok) else None
    return tok if _is_http(tok) else None


_bash_installed = False


def install_bash_redirect() -> bool:
    """patch TerminalTools.execute_bash：拦截 start/explorer <url> 转交内置浏览器

    幂等：已注入过（含热重载遗留代理）→ 直接返回。
    """
    global _bash_installed
    if _bash_installed:
        return True
    try:
        from app.tools.terminal_tools import TerminalTools
    except Exception:
        return False  # 主程序版本无该模块（如测试环境）→ 跳过，不影响其他功能

    if getattr(TerminalTools.execute_bash, "_drifox_redirect", False):
        _bash_installed = True
        return True

    orig = TerminalTools.execute_bash

    def _redirect_execute_bash(self, command: str, timeout: int = 120):
        """代理 execute_bash：start/explorer <url|html> → 内置浏览器；其余照常执行"""
        if isinstance(command, str):
            try:
                url = _extract_start_url(command)
            except Exception:
                url = None
            if url is not None and should_intercept(url, "shell"):
                logger.info(f"[browser-redirect] bash 拦截 start 命令: {command!r} → {url}")
                if _open_in_browser_threadsafe(to_browser_url(url)):
                    from app.tools.result import ToolResult

                    return ToolResult(True, content=f"🌐 已在 DriFox 内置浏览器打开: {url}")
                logger.warning(f"[browser-redirect] 内置浏览器打开失败，回退原始命令: {command!r}")
        return orig(self, command, timeout)

    _redirect_execute_bash._drifox_redirect = True  # type: ignore[attr-defined]
    TerminalTools.execute_bash = _redirect_execute_bash
    _bash_installed = True
    return True
