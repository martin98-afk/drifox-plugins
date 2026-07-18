# -*- coding: utf-8 -*-
"""git-panel UI 组件入口 — Git 控制面板"""

import sys
from pathlib import Path

from loguru import logger


def register_ui(registry):
    """注册 git-panel 的 UI 组件

    热重载兼容：清理 sys.modules 中残留的子模块缓存。
    """
    # 清理旧子模块缓存（热重载兼容）
    safe_name = "git-panel".replace("-", "_")
    prefix = f"ui_plugin_{safe_name}."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    from .cards import GitPanelCard

    registry.register_floating_card(
        plugin_name="git-panel",
        card_id="git-panel",
        widget_class=GitPanelCard,
        container="bottom",
        title="Git 面板",
        default_visible=False,
    )

    logger.info("[git-panel] UI components registered")
