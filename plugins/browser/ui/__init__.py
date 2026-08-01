# -*- coding: utf-8 -*-
"""browser UI 组件入口

注册浮动卡片「浏览器」以及全部 function 命令：
- /browser           打开/聚焦浏览器（可带 URL 参数）
- /browser-new       新建标签页
- /browser-devtools  打开 DevTools（依赖任务 0 的 build.py DevTools 资源保留）
- /browser-incognito 打开隐身窗口

热重载语义（与 UIPluginRegistry.load_plugin 调用约定一致）：
1. 清理 sys.modules 中残留的 ui_plugin_browser.* 子模块缓存
2. 注册前清理 function handlers 中残留的旧引用（M2 修复：4 个 function handler）
3. 注册浮动卡片（自动注册 /browser 命令，handler 由 registry 默认绑定；
   handle_browser_command 静态方法会通过 FunctionCommandHandlers.register 覆盖，
   使其支持 URL 参数处理）
4. 调用 downloads.reset_handled_profiles()（M1 修复：清理上次重载残留的
   downloadRequested 信号连接，避免 Qt 端连接泄漏）
"""

import sys

from loguru import logger


def register_ui(registry):
    """注册 browser 插件的 UI 组件（浮动卡片 + function 命令）

    热重载兼容：
    - 清理 sys.modules 子模块缓存，避免 Python 用旧的 .pyc
    - 清理 function handlers 残留（M2 修复）
    - 清理 downloads 挂载的 profile 信号（M1 修复）
    """
    # 0) 安装外部链接重定向：主程序 http/https 外链默认打开到内置浏览器
    try:
        from .external_open import install_redirect

        install_redirect()
    except Exception:
        logger.exception("[browser] 外部链接重定向安装失败（不影响其余功能）")

    # 0.5) 启动浏览器控制 HTTP 端点（供 MCP 服务器控制浏览器）
    try:
        from pathlib import Path as _Path
        from .control_server import start_control_server

        plugin_root = _Path(__file__).resolve().parent.parent
        start_control_server(plugin_root)
    except Exception:
        logger.exception("[browser] 控制端点启动失败（不影响其余功能）")

    # 1) 清理旧子模块缓存
    prefix = "ui_plugin_browser."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    # 2) M2 修复：清理 function handlers 中残留的旧引用（避免热重载后 handler
    #    被旧模块的闭包持有，导致 _CURRENT_CARD 指向已 deleteLater 的实例）
    from app.core.builtin_commands import FunctionCommandHandlers

    for cmd in ("browser-new", "browser-devtools", "browser-incognito"):
        FunctionCommandHandlers._handlers.pop(cmd, None)
    # browser 命令由 register_floating_card 自动注册，但 handler 我们要用静态方法
    # 覆盖以支持 URL 参数。这里先 pop，让下面 register 时填入新静态方法。
    FunctionCommandHandlers._handlers.pop("browser", None)

    # 3) M1 修复：清理下载 handler 挂载的 profile 信号
    try:
        from .downloads import reset_handled_profiles

        reset_handled_profiles()
    except Exception:
        pass

    from .browser_window import BrowserWindowCard

    # 4) 注册浮动卡片（自动注册对应命令 /browser）
    registry.register_floating_card(
        plugin_name="browser",
        card_id="browser",
        widget_class=BrowserWindowCard,
        container="right",
        title="浏览器",
        default_visible=False,
    )

    # 5) 注册 function 命令 handler（覆盖默认 toggle 行为，支持 URL 参数等）
    FunctionCommandHandlers.register("browser", BrowserWindowCard.handle_browser_command)
    FunctionCommandHandlers.register("browser-new", BrowserWindowCard.handle_browser_new)
    FunctionCommandHandlers.register("browser-devtools", BrowserWindowCard.handle_browser_devtools)
    FunctionCommandHandlers.register("browser-incognito", BrowserWindowCard.handle_browser_incognito)

    logger.info("[browser] UI components registered")