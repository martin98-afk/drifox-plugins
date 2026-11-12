# -*- coding: utf-8 -*-
"""context-insight UI 入口。

只注册一个载体：**全页覆盖卡** ``context-insights``（container=full）。
页内两个顶级 tab：
- **洞察**：跨会话 KPI、7 日用量、热力图、计费组成、台账与会话卡；
- **会话上下文**：当前会话的概览/组成/趋势/事件/浏览/文件/命令/编队。

左侧栏入口「上下文洞察」，短命令 ``/context`` 直接打到「会话上下文」tab；
``/context-insights`` 等自动命令由浮动卡注册联动生成。
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

PLUGIN_NAME = "context-insight"
CARD_INSIGHTS = "context-insights"


def _icons() -> tuple[str, str]:
    root = Path(__file__).resolve().parent.parent
    return str(root / "icon.svg"), str(root / "icon_dark.svg")


def _open_session_tab(registry) -> None:
    """打开洞察页并切到「会话上下文」tab。"""
    try:
        show = getattr(registry, "_show_floating_card", None)
        if callable(show):
            show(CARD_INSIGHTS)
        else:
            registry.toggle_floating_card(CARD_INSIGHTS)
        widget = registry.get_floating_card_widget(CARD_INSIGHTS)
        if widget is not None and hasattr(widget, "show_tab"):
            widget.show_tab("session")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[context-insight] 打开会话上下文 tab 失败: {e}")


def register_ui(registry) -> None:
    safe = PLUGIN_NAME.replace("-", "_")
    prefix = f"ui_plugin_{safe}."
    for name in [k for k in sys.modules if k.startswith(prefix)]:
        del sys.modules[name]

    from .insights import InsightsPage
    from .plugin_config import plugin_data_dir

    # 主线程预热数据目录：避免后台 worker 首次走 caps_for 的 adopted-thread 路径
    try:
        plugin_data_dir()
    except Exception:
        pass

    light, dark = _icons()

    registry.register_floating_card(
        plugin_name=PLUGIN_NAME,
        card_id=CARD_INSIGHTS,
        widget_class=InsightsPage,
        container="full",
        title="上下文洞察",
        default_visible=False,
        metadata={
            "icon_light": light,
            "icon_dark": dark,
            "full_card": True,
            "primary_entry": {
                "kind": "sidebar",
                "label": "上下文洞察",
                "icon_path": dark,
                "priority": 5,
            },
        },
    )

    # dsh-context 的 /context 短命令：直达「会话上下文」tab
    try:
        registry.register_ui_command(
            "context",
            "打开上下文洞察页（会话上下文）",
            lambda _args="": _open_session_tab(registry),
            owner=PLUGIN_NAME,
            override_external=False,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[context-insight] 注册 /context 命令失败: {e}")

    logger.info("[context-insight] UI 已注册：全页洞察卡（洞察 + 会话上下文）+ /context")


def unload_ui(registry) -> None:
    """卸载钩子：先停后台线程，再清模块缓存。"""
    try:
        instances = getattr(registry, "_card_widget_instances", {}) or {}
        for cards in list(instances.values()):
            widget = cards.get(CARD_INSIGHTS) if hasattr(cards, "get") else None
            if widget is not None and hasattr(widget, "shutdown"):
                try:
                    widget.shutdown()
                except Exception:
                    pass
    except Exception:
        pass
    try:
        from .tooltip import destroy_chart_tooltip

        destroy_chart_tooltip()
    except Exception:
        pass
    safe = PLUGIN_NAME.replace("-", "_")
    prefix = f"ui_plugin_{safe}."
    for name in [k for k in sys.modules if k.startswith(prefix)]:
        del sys.modules[name]
