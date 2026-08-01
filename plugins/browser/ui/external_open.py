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

拦截规则：
- 仅 http/https 拦截 → 打开浏览器浮动卡片并新开标签页导航
- 其余（file:/mailto:/本地路径等）→ 原系统逻辑
- 浏览器插件未注册 / 卡片不可用 → 回退系统浏览器

幂等：热重载时 register_ui 再次执行，通过标记检测避免重复嵌套 patch。
"""

import re
import webbrowser
from typing import Any, Optional

# ── 幂等标记 ──────────────────────────────────────────────
_installed = False
_orig_webbrowser_open: Any = None
_orig_qdesktop_openurl: Any = None


def _is_http(url: str) -> bool:
    """仅拦截 http/https（scheme 大小写不敏感）"""
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
            return False  # 浏览器插件未注册 → 回退系统浏览器

        target = normalize_url(url) or url

        # 确保浏览器卡片可见（已可见则不重复触发 toggle 关闭）
        cm = CardManager.get_instance()
        visible = any(cm.is_card_visible("browser", wid) for wid in cm.get_all_windows())
        if not visible:
            registry.toggle_floating_card("browser")

        card = _get_current_card()
        if card is None:
            return False
        card._new_tab(target)  # 总是新开标签页
        return True
    except Exception:
        return False


def _open_in_browser_threadsafe(url: str) -> bool:
    """线程安全入口：非 UI 线程调用时调度到主线程再打开"""
    try:
        from PyQt5.QtCore import QThread, QTimer
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None and QThread.currentThread() != app.thread():
            QTimer.singleShot(0, lambda: _open_in_browser(url))
            return True  # 已接管，稍后异步在主线程打开
    except Exception:
        pass
    return _open_in_browser(url)


def _redirect_webbrowser_open(url, new=0, autoraise=True):
    """webbrowser.open 代理：http/https → 内置浏览器，其余走系统"""
    if isinstance(url, str) and _is_http(url):
        if _open_in_browser_threadsafe(url):
            return True
    return _orig_webbrowser_open(url, new, autoraise)


class _RedirectDesktopServices:
    """QDesktopServices 代理类：openUrl 拦截 http/https 到内置浏览器"""

    _drifox_redirect = True  # 幂等标记：热重载检测已 patch

    @staticmethod
    def openUrl(url) -> bool:
        try:
            url_str = url.toString() if hasattr(url, "toString") else str(url)
        except Exception:
            url_str = str(url)
        if _is_http(url_str):
            if _open_in_browser_threadsafe(url_str):
                return True
        return _orig_qdesktop_openurl(url)


def install_redirect() -> bool:
    """安装外部链接重定向（register_ui 时调用）。返回是否完成注入。

    幂等：已注入过（含上次热重载遗留的代理）→ 直接返回，避免嵌套 patch。
    """
    global _installed, _orig_webbrowser_open, _orig_qdesktop_openurl

    # 已注入标记（本模块实例 / 热重载遗留代理）
    if _installed or getattr(webbrowser.open, "_drifox_redirect", False):
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
    install_bash_redirect()

    _installed = True
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
    """从 start / explorer 命令中提取 URL，非 URL 场景返回 None

    支持形态：
    - start https://example.com
    - start "" https://example.com
    - start /min https://example.com
    - cmd /c start http://localhost:8080
    - explorer "https://example.com"
    非 URL（start notepad.exe / explorer D:\\folder）→ None，不拦截。
    """
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
        """代理 execute_bash：start/explorer <url> → 内置浏览器；其余照常执行"""
        if isinstance(command, str):
            try:
                url = _extract_start_url(command)
            except Exception:
                url = None
            if url is not None:
                if _open_in_browser_threadsafe(url):
                    from app.tools.result import ToolResult

                    return ToolResult(True, content=f"🌐 已在 DriFox 内置浏览器打开: {url}")
        return orig(self, command, timeout)

    _redirect_execute_bash._drifox_redirect = True  # type: ignore[attr-defined]
    TerminalTools.execute_bash = _redirect_execute_bash
    _bash_installed = True
    return True
