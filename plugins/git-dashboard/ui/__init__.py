# -*- coding: utf-8 -*-
"""Git Dashboard 浮动卡片注册入口"""


def register_ui(registry) -> None:
    """注册 git-dashboard 浮动卡片

    Args:
        registry: UIPluginRegistry 单例
    """
    from .cards import GitDashboardCard

    registry.register_floating_card(
        plugin_name="git-dashboard",
        card_id="git-dashboard",
        widget_class=GitDashboardCard,
        container="bottom",
        title="Git 仪表盘",
        default_visible=False,
    )
