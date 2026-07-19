# -*- coding: utf-8 -*-
"""memory-match UI 组件入口"""

import sys
from pathlib import Path
from loguru import logger


def register_ui(registry):
    """注册记忆翻牌插件的 UI 组件

    - 注册 MemoryMatchCard 为浮动卡片（自动创建 /memory-match 命令）
    """
    # 清理旧子模块缓存（热重载兼容）
    prefix = "ui_plugin_memory_match."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    from .memory_card import MemoryMatchCard

    registry.register_floating_card(
        plugin_name="memory-match",
        card_id="memory-match",
        widget_class=MemoryMatchCard,
        container="bottom",
        title="记忆翻牌",
        default_visible=False,
    )

    logger.info("[memory-match] UI components registered")