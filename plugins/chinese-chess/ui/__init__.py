# -*- coding: utf-8 -*-
"""chinese-chess UI 组件入口"""

import sys
from loguru import logger


def register_ui(registry):
    """注册中国象棋插件的 UI 组件

    - 注册 ChessCard 为浮动卡片（自动创建 /chinese-chess 命令）
    """
    # 清理旧子模块缓存（热重载兼容）
    prefix = "ui_plugin_chinese-chess."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    from .chess_board import ChessCard

    registry.register_floating_card(
        plugin_name="chinese-chess",
        card_id="chinese-chess",
        widget_class=ChessCard,
        container="bottom",
        title="中国象棋",
        default_visible=False,
    )

    logger.info("[chinese-chess] UI components registered")
