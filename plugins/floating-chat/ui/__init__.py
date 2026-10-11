# -*- coding: utf-8 -*-
"""floating-chat UI 入口：注册一个可随时呼出的对话悬浮窗（独立弹窗）。

交互：热键/命令 `/floating-chat:chat` 打开 → 输入即问 → 纯文本流式作答
→ 「打开完整会话」可拉起主窗加载该会话。

关键约束：
- 窗口壳由主程序 PluginWindow 提供（无边框 + 精简标题栏 + 主题 + 生命周期），
  插件只做客户区；「钉住」按钮由插件往标题栏布局插入（见 ChatPage.show_card）。
- 不自建全局热键：走主程序既有的命令快捷键机制（用户在快捷键管理器分配）。
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from .engine_bridge import PLUGIN_NAME

_WINDOW_ID = f"{PLUGIN_NAME}:chat"

_ICON_LIGHT = str(Path(__file__).resolve().parent.parent / "icon.svg")
_ICON_DARK = str(Path(__file__).resolve().parent.parent / "icon_dark.svg")


def _is_dark() -> bool:
    try:
        from qfluentwidgets import isDarkTheme

        return bool(isDarkTheme())
    except Exception:  # noqa: BLE001 — 主题库不可用时按深色兜底
        return True


def _ctx_provider() -> dict:
    """窗口上下文（每次调用现取主程序主题 token，保证主题切换后跟随）"""
    ctx: dict = {}
    try:
        from app.utils.design_tokens import Colors

        Colors.refresh()
        ctx["colors"] = {
            "text_primary": Colors.TEXT_PRIMARY,
            "text_secondary": Colors.TEXT_SECONDARY,
            "border": Colors.BORDER,
            "accent": Colors.TEXT_ACCENT,
            "content_bg": Colors.CONTENT_BG,
        }
    except Exception as e:  # noqa: BLE001 — token 不可用时由页面侧 fallback 接手
        logger.debug(f"[{PLUGIN_NAME}] 主题 token 读取失败: {e}")
    ctx["is_dark"] = _is_dark()
    return ctx


def open_chat_window():
    """打开/前置悬浮窗（供命令与其他入口联动）"""
    try:
        from app.plugins.registries.ui_plugin_registry import UIPluginRegistry

        return UIPluginRegistry.get_instance().open_window(_WINDOW_ID)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[{PLUGIN_NAME}] 打开悬浮窗失败: {e}")
        return None


def register_ui(registry) -> None:
    """注册独立弹窗。热重载时主程序重新调用本函数。"""
    # 热重载兼容：清理旧子模块缓存，确保从 .py 重新编译
    prefix = f"ui_plugin_{PLUGIN_NAME.replace('-', '_')}."
    for k in [k for k in sys.modules if k.startswith(prefix)]:
        del sys.modules[k]

    from .chat_page import (
        DEFAULT_HEIGHT,
        DEFAULT_WIDTH,
        MIN_HEIGHT,
        MIN_WIDTH,
        ChatPage,
    )

    registry.register_window(
        plugin_name=PLUGIN_NAME,
        window_id=_WINDOW_ID,
        widget_class=ChatPage,
        title="快速对话",
        icon_path=_ICON_DARK,
        width=DEFAULT_WIDTH,
        height=DEFAULT_HEIGHT,
        min_width=MIN_WIDTH,
        min_height=MIN_HEIGHT,
        context_provider=_ctx_provider,
    )

    # commands/floating-chat.md 声明的 FUNCTION 命令（命令名 = 文件名）：
    # 挂处理器后，快捷键管理器分配的按键走 _execute_command → 直达开窗。
    # dict 覆盖式注册，热重载重复调用幂等。
    try:
        from app.core.commands.builtin_commands import FunctionCommandHandlers

        FunctionCommandHandlers.register(PLUGIN_NAME, lambda _args="": open_chat_window())
    except Exception as e:  # noqa: BLE001 — 宿主无该 API 时退化为仅弹窗命令入口
        logger.warning(f"[{PLUGIN_NAME}] 命令处理器注册失败（快捷键入口不可用）: {e}")

    logger.info(f"[{PLUGIN_NAME}] 悬浮对话窗已注册（命令 /{_WINDOW_ID}）")
