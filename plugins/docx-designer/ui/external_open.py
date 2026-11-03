# -*- coding: utf-8 -*-
"""docx 文件拦截 — 将 docx 文件打开默认进入文档设计预览窗口

原理（monkey patch，模式与 browser/ui/external_open.py 同构，插件进程内执行）：
- patch ``os.startfile``：Windows 打开本地文件的「事实标准」入口；
  代理只拦 .docx，其余透传给安装时刻的入口函数（可能是 browser 的代理，
  因此两个插件无论谁先安装，链式透传都保持完整）。
- patch ``PyQt5.QtGui.QDesktopServices``：模块属性是单槽（非函数链），
  代理类包裹「安装时刻」的现有类（browser 代理类或原始类）实现链式透传。

与 browser 接管逻辑的兼容：
- 本代理函数/类用独立标记 ``_drifox_docx_redirect``（不用 browser 的
  ``_drifox_redirect``），browser 热重载接管时不会误判本代理为其遗留，
  而是走 orig 兜底分支把本代理存为其调用链一环 —— 嵌套安全。

拦截行为：
- .docx（大小写不敏感，含 file:// URL 解码）→ 打开 docx-designer 预览窗口
- 打开失败（解析失败/窗口不可用）→ 回退原始入口打开文件，保证文件仍可见
- 其余一切（.doc/.pdf/可执行等）→ 原样透传

热重载安全：原入口函数挂代理属性 ``_drifox_docx_orig_startfile`` /
``_drifox_docx_orig_class``；重复安装通过标记检测幂等。

⚠️ 本模块不 patch webbrowser.open（Windows 下其内部走 os.startfile，
已被覆盖）与 bash start/explorer（进程外 ShellExecute，无法拦截，
记录为已知简化）。
"""

import os
import sys
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote

from loguru import logger

# Qt 依赖延迟到工厂函数：本模块的拦截判定函数（_docx_local_path）
# 需在无 Qt 环境（系统 python 单测）下可 import

# ── 幂等标记 ──────────────────────────────────────────────
_installed = False
_orig_os_startfile: Any = None
_orig_qds_class: Any = None

_DISPATCHER: Any = None
_DISPATCHER_CLASS: Any = None


def _dispatcher_class():
    """惰性构造主线程派发器类（依赖 Qt；无 Qt 环境返回 None）"""
    global _DISPATCHER_CLASS
    if _DISPATCHER_CLASS is None:
        try:
            from PyQt5.QtCore import QObject, pyqtSignal
        except Exception:
            return None

        class _MainThreadDispatcher(QObject):
            """跨线程派发器：信号 AutoConnection 自动投递到主线程事件循环。"""

            _requested = pyqtSignal(object)

            def __init__(self):
                super().__init__()
                self._requested.connect(self._handle)

            def _handle(self, fn):
                try:
                    fn()
                except Exception:
                    logger.exception("[docx-redirect] 主线程派发任务异常")

            def call(self, fn):
                self._requested.emit(fn)

        _DISPATCHER_CLASS = _MainThreadDispatcher
    return _DISPATCHER_CLASS


def _get_dispatcher():
    """获取主线程派发器（须在主线程创建；不可用时返回 None 走直接调用）"""
    global _DISPATCHER
    if _DISPATCHER is None:
        try:
            from PyQt5.QtCore import QThread
            from PyQt5.QtWidgets import QApplication

            cls = _dispatcher_class()
            if cls is None:
                return None
            app = QApplication.instance()
            if app is None or QThread.currentThread() != app.thread():
                return None
            _DISPATCHER = cls()
        except Exception:
            return None
    return _DISPATCHER


# ── 目标判定 ──────────────────────────────────────────────

_DOCX_SUFFIX = ".docx"


def _docx_local_path(target: str) -> Optional[Path]:
    """若目标指向本地 .docx 文件返回其 Path，否则 None。

    接受磁盘路径（C:/a.docx）与 file:// URL（含 %20 等转义）。
    """
    t = (target or "").strip()
    if not t:
        return None
    if t.lower().startswith("file://"):
        t = unquote(t[len("file://"):])
        t = t.lstrip("/")  # file:///C:/x → C:/x；UNC（file://server/x）保留 // 前缀
        if t and not t[1:].startswith(":") and not t.startswith("//"):
            return None
    if not t.lower().endswith(_DOCX_SUFFIX):
        return None
    try:
        p = Path(t)
    except (OSError, ValueError):
        return None
    return p if p.is_absolute() else None


def _open_in_designer(path: Path) -> bool:
    """显示预览窗口并加载文件；失败返回 False（由调用方回退系统打开）。"""
    from app.plugins.registries.ui_plugin_registry import UIPluginRegistry

    registry = UIPluginRegistry.get_instance()
    registry.toggle_floating_card("docx-designer")
    card = registry.get_floating_card_widget("docx-designer")
    if card is None:
        # 兜底：模块级单例（热重载后 registry 缓存缺失时）
        try:
            from .docx_window import _get_current_card

            card = _get_current_card()
        except Exception:
            card = None
    if card is None:
        return False
    return bool(card.open_path(str(path)))


def open_in_system(path):
    """绕过全部拦截代理，系统级打开（供「用系统程序打开」菜单项）"""
    _shell_open(str(path))


def _try_intercept(target: Any) -> bool:
    """.docx 拦截决策：命中且窗口打开成功返回 True；否则 False（调用方透传）。"""
    try:
        s = target.toString() if hasattr(target, "toString") else str(target)
    except Exception:
        return False
    path = _docx_local_path(s)
    if path is None:
        return False

    def _open():
        try:
            if _open_in_designer(path):
                logger.info(f"[docx-redirect] 已拦截 → 文档设计预览: {path.name}")
                return
        except Exception:
            logger.exception("[docx-redirect] 预览打开异常")
        _fallback_open(path)

    disp = _get_dispatcher()
    if disp is not None:
        disp.call(_open)
    else:
        _open()
    return True  # 已接管：无论窗口成败都不再走系统入口（失败由 _fallback_open 兜底）


def _fallback_open(path: Path):
    """窗口打开失败时系统级打开（不走任何 startfile 代理，防回环）。"""
    logger.warning(f"[docx-redirect] 预览打开失败，系统级打开: {path}")
    _shell_open(str(path))


def _shell_open(path: str) -> bool:
    """系统级打开：不经过 webbrowser / QDesktopServices / os.startfile 任何代理。

    Windows 走 ShellExecuteW；macOS 走 open；Linux 桌面走 xdg-open。
    """
    try:
        if sys.platform == "win32":
            import ctypes

            rc = ctypes.windll.shell32.ShellExecuteW(None, "open", path, None, None, 1)
            if rc > 32:
                return True
            logger.warning(f"[docx-redirect] ShellExecuteW 失败 rc={rc}: {path[:80]}")
            return False
        if sys.platform == "darwin":
            import subprocess

            subprocess.Popen(["open", path])
            return True
        import subprocess

        subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        logger.exception(f"[docx-redirect] 系统级打开异常: {path[:80]}")
        return False


# ── 代理 ─────────────────────────────────────────────────

def _redirect_os_startfile(filepath):
    """os.startfile 代理：拦 .docx → 预览窗口；其余透传（可能透传给 browser 代理）。"""
    try:
        if _try_intercept(filepath):
            return None
    except Exception:
        logger.exception("[docx-redirect] startfile 拦截决策异常，放行")
    return _orig_os_startfile(filepath)


_redirect_os_startfile._drifox_docx_redirect = True  # type: ignore[attr-defined]


class _RedirectDesktopServices:
    """QDesktopServices 代理类：openUrl 拦 .docx，其余转交安装时刻的现有类。

    注意模块属性是单槽：本类包裹 prev_class（browser 代理类或原始类），
    保证替换后 browser 侧拦截链不断。
    """

    _drifox_docx_redirect = True
    _drifox_docx_orig_class: Any = None

    @staticmethod
    def openUrl(url) -> bool:
        try:
            s = url.toString() if hasattr(url, "toString") else str(url)
        except Exception:
            s = str(url)
        try:
            if _docx_local_path(s) is not None:
                _try_intercept(s)
                return True
        except Exception:
            logger.exception("[docx-redirect] openUrl 拦截决策异常，放行")
        orig_class = _RedirectDesktopServices._drifox_docx_orig_class
        return orig_class.openUrl(url)


# ── 安装 ─────────────────────────────────────────────────


def _get_qtgui():
    try:
        import PyQt5.QtGui as _qtgui

        return _qtgui
    except Exception:
        return None


def install_docx_redirect() -> bool:
    """安装 docx 文件拦截（register_ui 时调用）。幂等。

    嵌套原则：把「安装时刻」的入口函数/类原样存为 orig（无论是原始实现
    还是 browser 已装的代理），本代理只处理 .docx、其余原样转交。
    """
    global _installed, _orig_os_startfile, _orig_qds_class

    if _installed:
        _get_dispatcher()
        return True

    _get_dispatcher()

    # 1) patch os.startfile（Windows；其余平台无此入口直接跳过）
    if hasattr(os, "startfile"):
        prev_sf = os.startfile
        if not getattr(prev_sf, "_drifox_docx_redirect", False):
            if _orig_os_startfile is None:
                _orig_os_startfile = prev_sf
            _redirect_os_startfile._drifox_docx_orig_startfile = _orig_os_startfile  # type: ignore[attr-defined]
            os.startfile = _redirect_os_startfile  # type: ignore[assignment]
            logger.info("[docx-redirect] os.startfile 代理已安装")

    # 2) patch PyQt5.QtGui.QDesktopServices（代理类包裹现有类）
    qtgui = _get_qtgui()
    if qtgui is not None:
        prev_qds = qtgui.QDesktopServices
        if not getattr(prev_qds, "_drifox_docx_redirect", False):
            if _orig_qds_class is None:
                _orig_qds_class = prev_qds
            _RedirectDesktopServices._drifox_docx_orig_class = _orig_qds_class
            qtgui.QDesktopServices = _RedirectDesktopServices
            logger.info("[docx-redirect] QDesktopServices 代理已安装")

    _installed = True
    return True
