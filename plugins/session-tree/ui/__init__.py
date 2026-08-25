# -*- coding: utf-8 -*-
"""session-tree UI 组件入口

浮动卡片：左侧停靠面板，按时间分组展示当前项目的会话列表（类 Codex 桌面版）。
"""

import sys

from loguru import logger


def register_ui(registry):
    """注册 session-tree 的 UI 组件

    热重载兼容：
    清理 sys.modules 中残留的子模块缓存，确保 Python 重新从 .py 源文件编译。
    """
    prefix = "ui_plugin_session_tree."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    from .session_tree import SessionTreeCard

    # 注册浮动卡片
    # container="left"：停靠在 Tab 窗口左侧停靠区（与 project-side-rail 同侧），
    # 宽度可由 dockSplitter 拖拽调整
    registry.register_floating_card(
        plugin_name="session-tree",
        card_id="session-tree",
        widget_class=SessionTreeCard,
        container="left",
        title="会话",
        default_visible=True,
    )
    logger.info("[session-tree] UI components registered")
