# -*- coding: utf-8 -*-
"""twin-chat UI 组件入口

注册浮动卡片「⚡ 并发对话」以及 /twin-chat 命令（register_floating_card 自动联动）：
- /twin-chat  打开/隐藏并发对话卡片（卡片内嵌第二对话窗口实例）

热重载语义（与 UIPluginRegistry.load_plugin 调用约定一致）：
1. 清理 sys.modules 中残留的 ui_plugin_twin_chat.* 子模块缓存
2. 注册浮动卡片（自动注册 /twin-chat 命令）
"""

import sys

from loguru import logger


def register_ui(registry):
    """注册 twin-chat 插件的 UI 组件（浮动卡片）"""
    # 1) 清理旧子模块缓存，避免热重载后 Python 复用旧 .pyc
    prefix = "ui_plugin_twin_chat."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    from .twin_card import TwinChatCard

    # 2) 注册浮动卡片（自动注册对应命令 /twin-chat）
    registry.register_floating_card(
        plugin_name="twin-chat",
        card_id="twin-chat",
        widget_class=TwinChatCard,
        container="right",
        title="⚡ 并发对话",
        default_visible=False,
    )
    logger.info("[twin-chat] UI components registered")


def unload_ui(registry):
    """插件卸载/热重载回调（释放内嵌的第二对话窗口）"""
    try:
        from .twin_card import TwinChatCard

        card = TwinChatCard._instance
        if card is not None:
            card.cleanup()
    except Exception:
        pass

