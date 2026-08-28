# -*- coding: utf-8 -*-
"""marketplace-recommend — 欢迎卡片插件推荐页签

注册两个扩展点：
- register_welcome_tab    欢迎卡片新页签「插件推荐」：随机推荐市场未安装热门插件
- register_welcome_action 接管页签 HTML 的点击动作（mkr-install / mkr-shuffle）

主程序侧要求：handle_recommended_question 支持未知 action 派发
（UIPluginRegistry.dispatch_welcome_action，主程序 ≥ 本次配套改动版本）。
"""

import sys

from loguru import logger

_PREFIX = "marketplace-recommend."


def register_ui(registry):
    """UI 注册入口（PluginToolLoader 反射调用）"""
    # 热重载：清理本插件旧子模块，避免旧 __pycache__/闭包残留
    stale = [k for k in sys.modules if k.startswith(_PREFIX)]
    for k in stale:
        del sys.modules[k]

    from .actions import ACTIONS
    from .render import _ACTION_INSTALL, _ACTION_SHUFFLE, render_recommend

    registry.register_welcome_tab(
        plugin_name="marketplace-recommend",
        mode_key="mkt-recommend",
        label="插件推荐",
        render_func=render_recommend,
        priority=0,
        metadata={"description": "随机推荐插件市场未安装的热门插件，点击直接安装"},
    )
    if hasattr(registry, "register_welcome_action"):
        for action, handler in ACTIONS.items():
            registry.register_welcome_action(
                plugin_name="marketplace-recommend",
                action=action,
                handler=handler,
            )
    else:
        # 旧主程序无 welcome action 扩展点：页签可显示，点击安装/换一批不可用（需升级主程序）
        logger.warning(
            "[marketplace-recommend] 主程序缺少 register_welcome_action 扩展点，"
            "点击安装/换一批不可用——请升级并重启 DriFox"
        )
    # 预热：注册后立即后台拉市场数据（首次打开欢迎卡片时大概率已就绪）
    from . import render

    render._get_marketplace_data()
