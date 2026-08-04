# -*- coding: utf-8 -*-
"""ip-switcher UI 组件入口

注册浮动卡片「IP 换绑监控」并安装 monkey patch：
- /ip-switcher           打开/聚焦仪表盘
- register_ui 时安装 OpenAI patch（幂等）

热重载语义（对齐 UIPluginRegistry.load_plugin 约定）：
1. 清理 sys.modules 残留子模块缓存
2. 清理 function handlers 残留
3. 安装 patch（幂等标记防嵌套）
4. 注册浮动卡片
5. 懒启动代理池（主循环空闲后）
"""

import sys

from loguru import logger


def register_ui(registry):
    """注册 ip-switcher 插件的 UI 组件（浮动卡片 + monkey patch）"""
    # 0) 探测系统内置 opencode 免费 provider（仅日志提示，不写任何配置）
    try:
        from .config import discover_opencode_free_provider

        free_provider = discover_opencode_free_provider()
        if free_provider:
            logger.info(
                "[ip-switcher] 发现内置 opencode 免费 provider: "
                f"{len(free_provider['models'])} 模型 / {free_provider['url']}"
            )
        else:
            logger.warning("[ip-switcher] 未发现系统内置 opencode 免费 provider")
    except Exception:
        logger.exception("[ip-switcher] opencode 免费 provider 探测失败（不影响其余功能）")

    # 0.5) 安装 monkey patch：白名单模型走代理 + 429 换 IP 重试
    try:
        from .ip_redirect import install_redirect

        install_redirect()
    except Exception:
        logger.exception("[ip-switcher] monkey patch 安装失败（不影响卡片注册）")

    # 1) 清理旧子模块缓存
    prefix = "ui_plugin_ip_switcher."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    # 2) 清理 function handlers 残留
    try:
        from app.core.builtin_commands import FunctionCommandHandlers

        FunctionCommandHandlers._handlers.pop("ip-switcher", None)
    except Exception:
        pass

    # 3) 懒启动代理池（后台，不阻塞注册）
    try:
        from PyQt5.QtCore import QTimer

        def _lazy_start():
            try:
                from .config import get_config
                from .proxy_pool import get_manager
                from .state import get_state

                cfg = get_config()
                if cfg.get("enabled"):
                    manager = get_manager()
                    get_state().set_pool_state("starting")
                    # fetch_and_check=True：首次自动抓取+检测代理
                    ok = manager.start(fetch_and_check=True)
                    if ok:
                        # 平时保持同一 IP（sticky），仅限流时切换
                        manager.set_mode("sticky")
                        stats = manager.get_stats()
                        cur = (stats or {}).get("current")
                        if cur:
                            get_state().set_current_ip(cur)
                        get_state().set_pool_state("ok")
                        logger.info("[ip-switcher] 代理池就绪 (sticky 模式)")
                    else:
                        get_state().set_pool_state("error")
                        logger.error("[ip-switcher] 代理池启动失败")
            except Exception:
                logger.exception("[ip-switcher] 代理池启动失败")

        QTimer.singleShot(500, _lazy_start)
    except Exception:
        logger.exception("[ip-switcher] 代理池启动调度失败")

    # 4) 注册浮动卡片（自动注册 /ip-switcher 命令）
    from .ip_switcher_card import IPSwitcherCard

    registry.register_floating_card(
        plugin_name="ip-switcher",
        card_id="ip-switcher",
        widget_class=IPSwitcherCard,
        container="right",
        title="IP自动换绑",
        default_visible=False,
    )

    logger.info("[ip-switcher] UI components registered")


def unload_ui(registry):
    """插件卸载/热重载回调（由 UIPluginRegistry.unload_plugin 调用）

    在注册表清理前执行，用于释放外部资源：
    1. 停止代理池子进程（杀残留进程）
    2. 卸载 monkey patch（恢复 openai 原始方法）

    ⚠️ 此函数在旧模块上下文中执行——热重载时 sys.modules 里
    还是旧模块实例，get_manager()/uninstall_redirect() 均访问旧单例，
    因此能拿到旧子进程句柄并正确停止。
    """
    try:
        from .proxy_pool import get_manager

        get_manager().stop()
    except Exception as e:
        logger.warning(f"[ip-switcher] unload_ui 停止代理池失败: {e}")
    try:
        from .ip_redirect import uninstall_redirect

        uninstall_redirect()
    except Exception as e:
        logger.warning(f"[ip-switcher] unload_ui 卸载 patch 失败: {e}")
