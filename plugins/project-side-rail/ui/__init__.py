# -*- coding: utf-8 -*-
"""project-side-rail UI 组件入口

悬浮竖向 icon 列表 — 停靠在 Tab 窗口左侧停靠区（侧边栏右侧），
用于快速切换 DriFox 项目。
"""

import sys
from pathlib import Path

from loguru import logger


def register_ui(registry):
    """注册 project-side-rail 的 UI 组件

    热重载兼容：
    清理 sys.modules 中残留的子模块缓存，确保 Python 重新从 .py 源文件编译。
    """
    # 清理旧子模块缓存（避免热重载时 Python 用旧 sys.modules 缓存）
    prefix = "ui_plugin_project_side_rail."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    from .project_rail import ProjectSideRailCard

    # 注册浮动卡片
    # container="left"：停靠在 Tab 窗口左侧停靠区，宽度可由 dockSplitter 拖拽调整
    # （视觉上正好位于侧边栏(_tab_frame)与右边圆角矩形(_chat_frame)之间）
    registry.register_floating_card(
        plugin_name="project-side-rail",
        card_id="project-side-rail",
        widget_class=ProjectSideRailCard,
        container="left",
        title="项目切换",
        default_visible=True,
    )
    logger.info("[project-side-rail] UI components registered")
