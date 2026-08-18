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
- patch ``os.startfile``：Windows 下打开本地文件的「事实标准」入口，
  绕过 webbrowser/QDesktopServices（如直接 ``os.startfile("C:/x.html")``）。
  修复「本地 HTML 文件拦截不生效」的根因之一：原本只 patch 了 webbrowser.open，
  而 ``webbrowser.WindowsDefault.open`` 内部就是 ``os.startfile``；
  对于未走 webbrowser 的调用方（如某些工具直接 ``os.startfile``）则完全漏过。
- patch ``TerminalTools.execute_bash``：拦截大模型通过 bash 执行的
  ``start <url>`` / ``cmd /c start <url>`` / ``explorer <url>``，
  同样转交内置浏览器（用户明确要求大模型 start 开网页也走插件浏览器）。

拦截行为（配置驱动，见 redirect_config.py）：
- 全局开关 enabled：总闸，关闭后一切放行
- intercept_system：拦截 webbrowser/QDesktopServices 的 http/https 外链
- intercept_shell：拦截 bash start/explorer <url>
- intercept_html：拦截本地 html 文件（file:// / os.startfile / 磁盘 .html 路径）
  → 内置浏览器（修复原实现「打开 html 文件不拦截」的问题）
- 其余（file 非 html / mailto:/本地可执行文件等）→ 原系统逻辑
- 浏览器插件未注册 / 卡片不可用 → 回退系统浏览器
- 拦截执行时会在浏览器底部状态栏打一条提示，方便用户感知「拦截是否真的生效」

幂等：热重载时 register_ui 再次执行，通过标记检测避免重复嵌套 patch。
"""

import os
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
_orig_os_startfile: Any = None


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


def _open_in_browser(url: Any) -> bool:
    """尝试用内置浏览器打开链接：显示浏览器卡片 + 新开标签页导航

    浏览器不可用（插件未注册 / 卡片创建失败）返回 False，由调用方回退系统。
    """
    # 先规范化（Path / QUrl / 含空白 str → 字符串 + file:// URL）
    from .redirect_config import _normalize_to_str

    url = _normalize_to_str(url) if url else url
    try:
        from app.core.ui_plugin_registry import UIPluginRegistry
        from app.widgets.cards.card_manager import CardManager
        from .browser_window import _get_current_card
        from .url_bar import normalize_url

        registry = UIPluginRegistry.get_instance()
        if "browser" not in getattr(registry, "_floating_cards", {}):
            logger.warning(f"[browser-redirect] browser 卡片未注册，回退系统浏览器: {url}")
            return False  # 浏览器插件未注册 → 回退系统浏览器

        # http/https 走 normalize_url（地址栏 URL 规范化），file:// 直接用
        if url and url.lower().startswith("file://"):
            target = url
        else:
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


def _notify_status(text: str) -> None:
    """在浏览器底部状态栏打一条拦截结果反馈（静默失败：浏览器卡片未注册也行）

    用 QTimer.singleShot 派发到主线程，避免后台线程崩溃。
    用户看到这条提示就明确知道「拦截是否真的生效」。
    """
    try:
        from PyQt5.QtCore import QTimer
        from .browser_window import _get_current_card

        def _apply():
            card = _get_current_card()
            if card is not None and hasattr(card, "_set_status"):
                card._set_status(text)

        QTimer.singleShot(0, _apply)
    except Exception:
        pass


def _redirect_webbrowser_open(url, new=0, autoraise=True):
    """webbrowser.open 代理：按配置拦截 http/https + 本地 html → 内置浏览器

    接受 str / Path / QUrl 等任意类型（should_intercept 内部已统一规范化）。
    """
    if should_intercept(url, "system"):
        target = to_browser_url(url)
        if _open_in_browser_threadsafe(target):
            _notify_status(f"🛡 已拦截 → 内置浏览器: {target[:80]}")
            return True
        _notify_status(f"⚠ 拦截失败回退系统: {target[:80]}")
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
            target = to_browser_url(url_str)
            if _open_in_browser_threadsafe(target):
                _notify_status(f"🛡 已拦截 → 内置浏览器: {target[:80]}")
                return True
            _notify_status(f"⚠ 拦截失败回退系统: {target[:80]}")
        return _orig_qdesktop_openurl(url)


def _redirect_os_startfile(filepath):
    """os.startfile 代理：拦截本地 html 文件 → 内置浏览器

    Windows 上 ``os.startfile("C:/test.html")`` 走 ShellExecute 直接打开关联程序，
    不经过 webbrowser.open / QDesktopServices，因此必须额外 patch。
    非 Windows 平台 os.startfile 不存在（直接调用原函数）。
    """
    if should_intercept(filepath, "startfile"):
        target = to_browser_url(filepath)
        if _open_in_browser_threadsafe(target):
            _notify_status(f"🛡 已拦截 → 内置浏览器: {target[:80]}")
            return None  # 已拦截：吞掉 os.startfile 调用
        _notify_status(f"⚠ 拦截失败回退系统: {target[:80]}")
    return _orig_os_startfile(filepath)


def install_redirect() -> bool:
    """安装外部链接重定向（register_ui 时调用）。返回是否完成注入。

    幂等：已注入过（含上次热重载遗留的代理）→ 直接返回，避免嵌套 patch。
    """
    global _installed, _orig_webbrowser_open, _orig_qdesktop_openurl, _orig_os_startfile

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

    # 3) patch os.startfile（Windows：本地文件打开的「事实标准」入口）
    #    已注入（热重载遗留）→ 跳过避免嵌套 patch
    if hasattr(os, "startfile") and not getattr(os.startfile, "_drifox_redirect", False):
        _orig_os_startfile = os.startfile
        _redirect_os_startfile._drifox_redirect = True  # type: ignore[attr-defined]
        os.startfile = _redirect_os_startfile  # type: ignore[assignment]

    # 4) patch TerminalTools.execute_bash：拦截 start <url> 等命令
    bash_ok = install_bash_redirect()

    # 5) 预创建主线程派发器（register_ui 在主线程执行，必须在此创建，
    #    否则工作线程首次调用 _get_dispatcher 会因不在主线程而拒绝创建）
    _get_dispatcher()

    _installed = True
    logger.info(
        f"[browser-redirect] 外部链接重定向已安装 "
        f"(bash拦截={'OK' if bash_ok else '跳过'}, "
        f"派发器={'OK' if _dispatcher is not None else '不可用'}, "
        f"os.startfile={'OK' if _orig_os_startfile is not None else 'N/A'})"
    )
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
                target = to_browser_url(url)
                if _open_in_browser_threadsafe(target):
                    _notify_status(f"🛡 bash 拦截 → 内置浏览器: {target[:80]}")
                    from app.tools.result import ToolResult

                    return ToolResult(True, content=f"🌐 已在 DriFox 内置浏览器打开: {url}")
                _notify_status(f"⚠ bash 拦截失败回退: {command[:80]}")
                logger.warning(f"[browser-redirect] 内置浏览器打开失败，回退原始命令: {command!r}")
        return orig(self, command, timeout)

    _redirect_execute_bash._drifox_redirect = True  # type: ignore[attr-defined]
    TerminalTools.execute_bash = _redirect_execute_bash
    _bash_installed = True
    return True
