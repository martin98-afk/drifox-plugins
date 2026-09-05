# -*- coding: utf-8 -*-
"""quick-screenshot UI 插件：输入框按钮 → 全屏选区截图 → 复制到剪贴板。

交互流：点按钮 → grabWindow 抓主屏底图 → 全屏遮罩窗拖框 → 松手复制剪贴板
→ InfoBar 提示。Esc/右键取消。单实例防护：重复点击先关旧遮罩窗。
按钮位置锚定新建会话按钮左侧（position="before:new_session"）。
右键按钮：隐藏主窗 → 延迟抓屏 → 选区 → 恢复主窗（截 DriFox 身后的画面）。
旧主程序无 on_right_click 参数时自动降级为纯左键。
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import Any, Dict

from loguru import logger

PLUGIN_NAME = "quick-screenshot"
_BUTTON_ID = "quick-screenshot"
_TOOLTIP = "选区截图（左键：截图｜右键：隐藏窗口截图）"
_TOOLTIP_BASIC = "选区截图（复制到剪贴板）"

# 主窗 hide 后等 DWM 合成刷新再抓屏的延迟（ms）
_HIDE_CAPTURE_DELAY_MS = 280

# 存活遮罩窗引用（模块级，单实例防护）
_active_overlay = None


def _icons_dir() -> Path:
    # ui/__init__.py -> ui/icons/
    return Path(__file__).resolve().parent / "icons"


def _clear_ref(*_args: Any) -> None:
    """遮罩窗 destroyed 后清引用（WA_DeleteOnClose → C++ 对象已销毁）。"""
    global _active_overlay
    _active_overlay = None


def _close_active_overlay() -> None:
    global _active_overlay
    if _active_overlay is not None:
        try:
            _active_overlay.close()
        except RuntimeError:
            pass  # C++ 对象已被 Qt 销毁
        _active_overlay = None


def _notify_copy_done(main_widget, pixmap) -> None:
    """复制成功提示：优先主程序 InfoBar（QToolTip 在 DriFox 内不可靠），兜底 QToolTip。"""
    msg = f"截图已复制到剪贴板 {pixmap.width()}×{pixmap.height()}"
    try:
        from qfluentwidgets import InfoBar, InfoBarPosition

        InfoBar.success(
            "选区截图",
            msg,
            parent=main_widget,
            position=InfoBarPosition.BOTTOM,
            duration=2500,
        )
    except Exception as e:  # noqa: BLE001 — InfoBar 失败不影响剪贴板结果
        logger.warning(f"[quick-screenshot] InfoBar 提示失败，降级 QToolTip: {e}")
        from PyQt5.QtGui import QCursor
        from PyQt5.QtWidgets import QToolTip

        QToolTip.showText(QCursor.pos(), msg)


def _restore_window(window) -> None:
    """恢复主窗显示并尝试抢回前台（退出中窗口已销毁则静默）。"""
    try:
        window.show()
        window.raise_()
        window.activateWindow()
    except RuntimeError:
        pass  # C++ 对象已被销毁（应用退出中）


def _on_screenshot_clicked(context: Dict[str, Any]) -> None:
    """按钮点击：抓主屏 → 全屏遮罩选区 → 剪贴板。"""
    global _active_overlay
    _close_active_overlay()  # 防叠加
    main_widget = context.get("main_widget")

    try:
        from PyQt5.QtGui import QCursor
        from PyQt5.QtWidgets import QApplication, QToolTip

        from .overlay import _ScreenshotOverlay  # 运行时由主程序以包形式加载

        screen = QApplication.primaryScreen()
        if screen is None:
            QToolTip.showText(QCursor.pos(), "截图失败：未找到主屏幕")
            return
        base = screen.grabWindow(0)
        if base.isNull():
            QToolTip.showText(QCursor.pos(), "截图失败：抓屏为空")
            return
        logger.info(f"[quick-screenshot] 抓屏完成: {base.width()}x{base.height()} dpr={base.devicePixelRatio()}")

        overlay = _ScreenshotOverlay(base, screen.geometry())
        _active_overlay = overlay

        def _on_captured(pixmap) -> None:
            # 存 QImage 而非 setPixmap：同进程剪贴板回读时 QPixmap 不走系统
            # CF_DIB 转换，paste 端拿到的类型是 QPixmap；转 QImage 保持通用语义
            QApplication.clipboard().setImage(pixmap.toImage())
            # 读回验证：确认 Qt 层剪贴板确有图像（定位"复制了但粘贴板空"类问题）
            back = QApplication.clipboard().image()
            logger.info(
                f"[quick-screenshot] 剪贴板写入: {pixmap.width()}x{pixmap.height()} "
                f"读回 isNull={back.isNull()} size={back.width()}x{back.height()}"
            )
            _notify_copy_done(main_widget, pixmap)

        overlay.captured.connect(_on_captured)
        overlay.cancelled.connect(lambda: logger.debug("[quick-screenshot] 选区已取消"))
        overlay.destroyed.connect(_clear_ref)
        overlay.show()
        logger.debug("[quick-screenshot] 选区遮罩窗已弹出")
    except Exception as e:  # noqa: BLE001 — 全流程兜底，不允许残留全屏置顶窗
        logger.error(f"[quick-screenshot] 启动选区截图失败: {e}")
        _close_active_overlay()


def _on_screenshot_hidden_clicked(context: Dict[str, Any]) -> None:
    """右键：隐藏 DriFox 主窗 → 延迟抓屏选区 → 完成/取消后恢复主窗。"""
    global _active_overlay
    _close_active_overlay()  # 防叠加
    main_widget = context.get("main_widget")
    window = main_widget.window() if main_widget is not None else None
    if window is None:
        _on_screenshot_clicked(context)  # 兼底退化为普通截图
        return
    window.hide()
    from PyQt5.QtCore import QTimer

    QTimer.singleShot(
        _HIDE_CAPTURE_DELAY_MS, lambda: _start_hidden_capture(context, window)
    )


def _start_hidden_capture(context: Dict[str, Any], window) -> None:
    """延迟抓屏（主窗已隐藏）：成功走遮罩选区，任何失败路径都恢复主窗。"""
    try:
        from PyQt5.QtGui import QCursor
        from PyQt5.QtWidgets import QApplication, QToolTip

        from .overlay import _ScreenshotOverlay

        screen = QApplication.primaryScreen()
        if screen is None:
            raise RuntimeError("未找到主屏幕")
        base = screen.grabWindow(0)
        if base.isNull():
            raise RuntimeError("抓屏为空")
        logger.info(
            f"[quick-screenshot] 隐藏主窗后抓屏: {base.width()}x{base.height()} "
            f"dpr={base.devicePixelRatio()}"
        )

        overlay = _ScreenshotOverlay(base, screen.geometry())
        global _active_overlay
        _active_overlay = overlay

        def _on_captured(pixmap) -> None:
            _restore_window(window)  # 先恢复主窗，InfoBar 挂在主窗上才可见
            QApplication.clipboard().setImage(pixmap.toImage())
            back = QApplication.clipboard().image()
            logger.info(
                f"[quick-screenshot] 剪贴板写入: {pixmap.width()}x{pixmap.height()} "
                f"读回 isNull={back.isNull()} size={back.width()}x{back.height()}"
            )
            _notify_copy_done(context.get("main_widget"), pixmap)

        overlay.captured.connect(_on_captured)
        overlay.cancelled.connect(lambda: _restore_window(window))
        overlay.destroyed.connect(_clear_ref)
        overlay.show()
        logger.debug("[quick-screenshot] 隐藏模式选区遮罩窗已弹出")
    except Exception as e:  # noqa: BLE001 — 失败必须恢复主窗，不允许窗口消失
        logger.error(f"[quick-screenshot] 隐藏窗口截图失败: {e}")
        _restore_window(window)
        from PyQt5.QtGui import QCursor
        from PyQt5.QtWidgets import QToolTip

        QToolTip.showText(QCursor.pos(), f"截图失败：{e}")


def register_ui(registry) -> None:
    """注册输入框按钮。热重载时主程序重新调用本函数。"""
    # 热重载兼容：清理旧子模块缓存（避免 Python 用旧 sys.modules 引用）
    prefix = "ui_plugin_quick_screenshot."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    icons = _icons_dir()
    # 旧主程序无 on_right_click 参数：signature 检测降级为纯左键模式
    try:
        params = inspect.signature(registry.register_input_button).parameters
        supports_right = "on_right_click" in params
    except (TypeError, ValueError):
        supports_right = False

    kwargs: Dict[str, Any] = dict(
        icon_path=str(icons / "screenshot.svg"),
        icon_light_path=str(icons / "screenshot_light.svg"),
        tooltip=_TOOLTIP if supports_right else _TOOLTIP_BASIC,
        on_click=_on_screenshot_clicked,
        position="before:new_session",
    )
    if supports_right:
        kwargs["on_right_click"] = _on_screenshot_hidden_clicked
    registry.register_input_button(PLUGIN_NAME, _BUTTON_ID, **kwargs)
    logger.info(
        "[quick-screenshot] 输入框按钮已注册（新建会话左侧）"
        + ("，右键=隐藏窗口截图" if supports_right else "，旧主程序无右键能力")
    )
