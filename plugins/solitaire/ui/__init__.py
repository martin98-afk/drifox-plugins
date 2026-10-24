# -*- coding: utf-8 -*-
"""Solitaire（接龙）UI 组件入口"""

import sys
from loguru import logger


def register_ui(registry):
    """注册接龙插件的 UI 组件

    - 注册 SolitaireCard 为浮动卡片（自动创建 /solitaire 命令）
    """
    # 清理旧子模块缓存（热重载兼容）
    prefix = "ui_plugin_solitaire."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    from .solitaire_card import SolitaireCard

    registry.register_floating_card(
        plugin_name="solitaire",
        card_id="solitaire",
        widget_class=SolitaireCard,
        container="bottom",
        title="接龙 Solitaire",
        default_visible=False,
    )

    logger.info("[solitaire] UI components registered")
