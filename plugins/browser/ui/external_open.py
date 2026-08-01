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

拦截规则：
- 仅 http/https 拦截 → 打开浏览器浮动卡片并新开标签页导航
- 其余（file:/mailto:/本地路径等）→ 原系统逻辑
- 浏览器插件未注册 / 卡片不可用 → 回退系统浏览器

幂等：热重载时 register_ui 再次执行，通过标记检测避免重复嵌套 patch。
"""

import webbrowser
from typing import Any

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

    _installed = True
    return True
