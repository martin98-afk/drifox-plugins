# -*- coding: utf-8 -*-
"""pixel-team-studio UI 组件入口"""

import sys

from loguru import logger


def register_ui(registry):
    """注册 pixel-team-studio 的 UI 组件（浮动卡片）"""
    # 清理旧子模块缓存（避免热重载时 Python 用旧 sys.modules 缓存）
    prefix = "ui_plugin_pixel_team_studio."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    from .cards import PixelTeamStudioCard

    # 注册浮动卡片（自动注册对应命令 /pixel-team-studio）
    registry.register_floating_card(
        plugin_name="pixel-team-studio",
        card_id="pixel-team-studio",
        widget_class=PixelTeamStudioCard,
        container="full",
        title="像素团队工作室",
        default_visible=False,
    )
    logger.info("[pixel-team-studio] UI components registered")
