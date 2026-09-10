# -*- coding: utf-8 -*-
"""git-panel UI 组件入口 — Git 控制面板

额外注册「Git 提交描述生成」设置卡（多行提示词编辑 + 模型下拉 + 恢复默认），
覆盖主程序 E1 自动卡（text 字段单行不便编辑长提示词）。
"""

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
        container="left",
        title="Git 面板",
        default_visible=False,
    )

    _register_config_card(registry)

    logger.info("[git-panel] UI components registered")


def _register_config_card(registry):
    """注册「Git 提交描述生成」设置卡（失败降级 E1 自动卡）。"""
    try:
        from .config_card import _CommitConfigCard

        registry.register_settings_card(
            "git-panel",
            "git-panel-config",
            "Git 提交描述生成",
            _CommitConfigCard,
            priority=1,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[git-panel] 设置卡注册失败（降级 E1 自动卡）: {e}")


def unload_ui(registry):
    """卸载钩子（当前无残留状态需要清理）"""
