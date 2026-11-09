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

    # 注册进程内 MCP handler：宿主 LocalMcpGateway 直接调本机工具，
    # 不再 spawn 外部 python 子进程（打包版不依赖系统解释器安装 mcp/httpx）。
    # bili_impl 的 vendor 重依赖 import 放后台线程，别卡 UI 装载。
    def _register_mcp():
        try:
            from app.plugins.sdk import caps_for

            register_mcp = caps_for("mcp.register", surface="ui")
            if register_mcp is None:
                logger.warning(
                    "[bili-scroll] mcp.register 能力不可用（宿主版本较旧或缺声明），MCP 工具不可用"
                )
                return
            from .mcp_handler import build_tools, mcp_handle

            register_mcp("bili", mcp_handle, tools=build_tools())
        except Exception:
            logger.exception("[bili-scroll] 注册进程内 MCP handler 失败（不影响其余功能）")

    try:
        import threading as _threading

        _threading.Thread(
            target=_register_mcp,
            daemon=True,
            name="bili-mcp-register",
        ).start()
    except Exception:
        logger.exception("[bili-scroll] MCP 注册线程启动失败（不影响其余功能）")

    logger.info("[bili-scroll] UI components registered")


def unload_ui(*_args):
    """宿主回调带插件名实参，签名须容忍（2026-10-30 实测 0 参签名会 TypeError）。"""
    try:
        from .controller import release_scheduler

        release_scheduler()
    except Exception:
        pass
    # MCP handler 由宿主 UIPluginRegistry.unload_plugin 按插件名统一注销，
    # 无需插件侧手动清理（gateway 侧 unregister_plugin 已覆盖热重载）。
    logger.info("[bili-scroll] UI components unloaded")
