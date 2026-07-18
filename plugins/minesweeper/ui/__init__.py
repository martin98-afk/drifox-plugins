# -*- coding: utf-8 -*-
"""minesweeper UI 组件入口"""

import sys
from pathlib import Path
from loguru import logger


def register_ui(registry):
    """注册扫雷插件的 UI 组件

    - 注册 MinesweeperCard 为浮動卡片（自动创建 /minesweeper 命令）
    """
    # 清理旧子模块缓存（热重载兼容）
    prefix = "ui_plugin_minesweeper."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    from .minesweeper_card import MinesweeperCard

    registry.register_floating_card(
        plugin_name="minesweeper",
        card_id="minesweeper",
        widget_class=MinesweeperCard,
        container="bottom",
        title="💣 扫雷",
        default_visible=False,
    )

    logger.info("[minesweeper] UI components registered")
