# -*- coding: utf-8 -*-
"""tetris UI 组件入口"""

import sys
from pathlib import Path
from loguru import logger


def register_ui(registry):
    """注册俄罗斯方块插件的 UI 组件

    - 注册 TetrisCard 为浮動卡片（自动创建 /tetris 命令）
    """
    # 清理旧子模块缓存（热重载兼容）
    prefix = "ui_plugin_tetris."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    from .tetris_card import TetrisCard

    registry.register_floating_card(
        plugin_name="tetris",
        card_id="tetris",
        widget_class=TetrisCard,
        container="bottom",
        title="🧱 俄罗斯方块",
        default_visible=False,
    )

    logger.info("[tetris] UI components registered")