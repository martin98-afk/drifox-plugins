# -*- coding: utf-8 -*-
"""bili-scroll UI 入口：注册浮动卡（container=full，/bili-scroll 打开）。"""

import sys
from pathlib import Path

from loguru import logger

# 插件根注入 sys.path（宿主 UI 加载器不注根，biliscroll_core 靠它可 import）
_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)


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

    # MCP 控制端点常驻（重依赖 import 放后台线程，别卡 UI 装载；
    # MCP 壳有 _wait_bridge 轮询兜底时序）
    try:
        import threading as _threading

        from .control_server import start_control_server

        _threading.Thread(
            target=start_control_server,
            args=(_PLUGIN_ROOT,),
            daemon=True,
            name="bili-control-boot",
        ).start()
    except Exception:
        logger.exception("[bili-scroll] MCP 控制端点启动失败（不影响其余功能）")

    logger.info("[bili-scroll] UI components registered")


def unload_ui(*_args):
    """宿主回调带插件名实参，签名须容忍（2026-10-30 实测 0 参签名会 TypeError）。"""
    try:
        from .controller import release_scheduler

        release_scheduler()
    except Exception:
        pass
    try:
        # 旧模块上下文读模块属性（browser 同款）：热重载时相对导入会撞
        # register_ui 的 sys.modules 清理时序
        mod = sys.modules.get("ui_plugin_bili_scroll.control_server")
        if mod is not None:
            mod.stop_control_server()
    except Exception:
        pass
    logger.info("[bili-scroll] UI components unloaded")
