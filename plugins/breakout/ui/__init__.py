# -*- coding: utf-8 -*-
"""breakout UI 组件入口"""

import sys
from pathlib import Path
from loguru import logger


def register_ui(registry):
    """注册打砖块插件的 UI 组件

    - 注册 BreakoutCard 为浮动卡片（自动创建 /breakout 命令）
    """
    # 清理旧子模块缓存（热重载兼容）
    prefix = "ui_plugin_breakout."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    from .breakout_card import BreakoutCard

    registry.register_floating_card(
        plugin_name="breakout",
        card_id="breakout",
        widget_class=BreakoutCard,
        container="bottom",
        title="🏓 打砖块",
        default_visible=False,
    )

    logger.info("[breakout] UI components registered")