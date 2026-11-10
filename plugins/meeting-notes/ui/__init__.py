# -*- coding: utf-8 -*-
"""meeting-notes UI 注册：整页（full 容器）会议纪要卡片 + 标题栏入口。

形态选择：full 卡不是浮层，而是整页替换内容区，左右分栏才能撑开；
标题栏常驻 tab 作为主入口（primary_entry），点一下就唤起，命令 /meeting-notes 同义。
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

PLUGIN_NAME = "meeting-notes"
CARD_ID = "meeting-notes"


def _icons() -> dict:
    root = Path(__file__).resolve().parent.parent
    out = {}
    for theme, name in (("light", "icon.svg"), ("dark", "icon_dark.svg")):
        p = root / name
        if p.exists():
            out[f"icon_{theme}"] = str(p)
    return out


def register_ui(registry) -> None:
    """注册 full 卡片。热重载时宿主会重新调用本函数。"""
    # 热重载兼容：清掉本插件旧子模块，避免 Python 复用已卸下的模块对象
    prefix = f"ui_plugin_{PLUGIN_NAME.replace('-', '_')}."
    for k in [k for k in sys.modules if k.startswith(prefix)]:
        del sys.modules[k]

    from .card import MeetingNotesCard

    metadata = {
        # 全窗口页：整页替换内容区（与设置卡同款）
        "full_card": True,
        # 已有标题栏入口，跳过侧栏兼容派生，避免重复条目
        "hide_sidebar": True,
        # 主入口：框架按此派生标题栏 tab（点击唤起卡片）
        "primary_entry": {"kind": "titlebar", "label": "会议", "priority": 20},
    }
    metadata.update(_icons())

    registry.register_floating_card(
        plugin_name=PLUGIN_NAME,
        card_id=CARD_ID,
        widget_class=MeetingNotesCard,
        container="full",
        title="会议纪要",
        default_visible=False,
        metadata=metadata,
    )
    _register_config_card(registry)
    logger.info("[meeting-notes] 已注册 full 卡片（标题栏入口「会议」+ 命令 /meeting-notes）")


def _register_config_card(registry) -> None:
    """注册自绘设置卡，覆盖 E1 自动卡（priority 1 > 0）。

    自动卡的 select 是静态 JSON，列不出用户实际配置的服务商/模型；提示词也
    需要把内置模板铺出来供微调。注册失败（旧宿主无此扩展点）静默降级回自动卡。
    """
    try:
        from .config_card import _MeetingNotesConfigCard

        registry.register_settings_card(
            PLUGIN_NAME,
            f"{PLUGIN_NAME}-config",
            "会议纪要配置",
            _MeetingNotesConfigCard,
            priority=1,
        )
    except Exception as e:  # noqa: BLE001 — 降级到 E1 自动卡，不影响主功能
        logger.warning(f"[meeting-notes] 自绘配置卡注册失败，降级 E1 自动卡: {e}")
