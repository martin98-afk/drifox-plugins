# -*- coding: utf-8 -*-
"""bili-scroll UI 入口：注册浮动卡（container=full，/bili-scroll 打开）。"""

import sys
from pathlib import Path

from loguru import logger


def register_ui(registry):
    """注册 UI 组件。

    热重载兼容：清掉本插件 ui 子模块的 sys.modules 残留，强制从源码重编译
    （防旧 __pycache__ 导致 NameError）。magpie 教训：注册期先 preheat
    dispatcher（幂等），保证值班轮后台线程首触 _dispatch 前单例已在主线程建好。
    """
    try:
        from app.plugins.capabilities.providers.ui_bridge import preheat_main_thread_dispatcher

        preheat_main_thread_dispatcher()
    except Exception:
        pass

    prefix = "ui_plugin_bili_scroll."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    from .cards import BiliScrollCard

    registry.register_floating_card(
        plugin_name="bili-scroll",
        card_id="bili-scroll",
        widget_class=BiliScrollCard,
        container="full",
        title="B站值班",
        default_visible=False,
    )

    # 峰谷调度器常驻（卡片开不开都生效；热重载经 unload_ui 停表）
    from .controller import ensure_scheduler

    ensure_scheduler()
    logger.info("[bili-scroll] UI components registered")


def unload_ui():
    try:
        from .controller import release_scheduler

        release_scheduler()
    except Exception:
        pass
    logger.info("[bili-scroll] UI components unloaded")
