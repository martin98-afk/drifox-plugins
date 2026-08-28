# -*- coding: utf-8 -*-
"""chinese-chess UI 组件入口"""

import sys
from loguru import logger


def register_ui(registry):
    """注册中国象棋插件的 UI 组件

    - 注册 ChessCard 为浮动卡片（自动创建 /chinese-chess 命令）
    - 注册设置卡（我方控制方式 / 红黑方模型）
    """
    # 清理旧子模块缓存（热重载兼容）
    # 注意：模块名由主程序 safe_name 生成，连字符转下划线 → 前缀必须是下划线
    prefix = "ui_plugin_chinese_chess."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    from .chess_board import ChessCard
    from . import config_card

    card_ref = registry.register_floating_card(
        plugin_name="chinese-chess",
        card_id="chinese-chess",
        widget_class=ChessCard,
        container="bottom",
        title="中国象棋",
        default_visible=False,
    )

    # 注册设置卡（容错：旧版主程序无此扩展点时降级）
    config_card._register_chess_config_card(registry)

    # 把 ChessCard 实例引用暴露给设置卡，让其 _on_change_external 回调能挂上去
    # —— 浮动卡片创建是延后的（用户开 /chinese-chess 才创建），
    # 所以注册期拿不到 ChessCard 实例，由 chess_card 自行在 __init__ 里 register。
    # 这里仅做钩子占位（保留扩展能力）。
    _ = card_ref

    logger.info("[chinese-chess] UI components registered")
