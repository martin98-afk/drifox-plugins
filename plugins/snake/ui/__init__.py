# -*- coding: utf-8 -*-
"""snake UI 组件入口"""

import sys
from pathlib import Path
from loguru import logger


def register_ui(registry):
    """注册贪吃蛇插件的 UI 组件

    - 注册 SnakeCard 为浮動卡片（自动创建 /snake 命令）
    """
    # 清理旧子模块缓存（热重载兼容）
    prefix = "ui_plugin_snake."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    from .snake_card import SnakeCard

    registry.register_floating_card(
        plugin_name="snake",
        card_id="snake",
        widget_class=SnakeCard,
        container="bottom",
        title="贪吃蛇",
        default_visible=False,
    )

    logger.info("[snake] UI components registered")