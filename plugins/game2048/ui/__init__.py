# -*- coding: utf-8 -*-
"""2048 UI 组件入口"""

import sys
from pathlib import Path
from loguru import logger


def register_ui(registry):
    """注册 2048 插件的 UI 组件

    - 注册 Game2048Card 为浮動卡片（自动创建 /game2048 命令）
    """
    # 清理旧子模块缓存（热重载兼容）
    prefix = "ui_plugin_game2048."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    from .game2048_card import Game2048Card

    registry.register_floating_card(
        plugin_name="game2048",
        card_id="game2048",
        widget_class=Game2048Card,
        container="bottom",
        title="2048",
        default_visible=False,
    )

    logger.info("[game2048] UI components registered")