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


def _get_loaded_submodule(name: str):
    """获取已加载的插件子模块对象（热重载安全）

    优先 sys.modules 缓存；缓存被 register_ui 清理后（其清理逻辑把
    control_server 等先行 import 的子模块一并删除），回退到父模块属性
    （from .xxx import ... 会把子模块挂到父模块 __dict__，清理 sys.modules
    缓存不影响该引用）。未加载过的惰性模块（如从未打开的 incognito/
    devtools）返回 None → 调用方跳过清理即可，保持幂等。
    """
    mod = sys.modules.get(f"{__name__}.{name}")
    if mod is not None:
        return mod
    pkg = sys.modules.get(__name__)
    return getattr(pkg, name, None) if pkg is not None else None


def unload_ui(registry):
    """插件卸载/热重载回调（由 UIPluginRegistry.unload_plugin 调用）

    在注册表清理前执行，用于释放外部资源（以通读代码发现的实际资源为准）：
    1. 停止浏览器控制 HTTP 服务器（daemon 线程 + 随机端口占用 + bridge.json）
    2. 清理 downloads 挂载的 profile 下载信号连接
    3. 关闭所有隐身窗口（释放 OTR profile）
    4. 关闭所有 DevTools 窗口（释放 devtools page 关联）
    5. 清空持久 Profile 单例引用（热重载避免旧 Profile 悬空）

    ⚠️ 此函数在旧模块上下文中执行——热重载时 sys.modules 里
    还是旧模块实例，从模块属性取到的仍是旧资源句柄，
    因此能拿到旧服务器句柄并正确停止（与 ip-switcher unload_ui 同语义）。

    注：不采用 from .xxx import ... 相对导入：register_ui 的缓存清理会
    删除 control_server 等子模块的 sys.modules 缓存，热重载时相对导入
    会重新从磁盘加载而报 No module named；此处改为直接读模块属性，
    未加载的惰性子模块跳过（幂等，无残留也无误报）。

    注：external_open 的外部链接重定向 patch 保持幂等长期生效
    （浏览器不可用时自动回退系统浏览器 _orig_webbrowser_open），
    且 QDesktopServices 原 sip 类引用未保存、无法可靠还原，
    故不强行恢复，避免破坏主程序外链行为。
    """
    # 1) 停止浏览器控制 HTTP 服务器（幂等：未启动则跳过）
    try:
        cs = _get_loaded_submodule("control_server")
        if cs is not None:
            server_ref = getattr(cs, "_server_ref", None)
            if server_ref:
                server = server_ref.get("server")
                if server is not None:
                    server.shutdown()
                    server.server_close()
                server_ref.clear()
    except Exception as e:
        logger.warning(f"[browser] unload_ui 停止控制端点失败: {e}")

    # 2) 清理下载 profile 信号连接（幂等）
    try:
        dl = _get_loaded_submodule("downloads")
        if dl is not None:
            dl.reset_handled_profiles()
    except Exception as e:
        logger.warning(f"[browser] unload_ui 清理下载信号失败: {e}")

    # 3) 关闭所有隐身窗口（释放 OTR profile）
    try:
        inc = _get_loaded_submodule("incognito")
        if inc is not None:
            inc.close_all_incognito_windows()
    except Exception as e:
        logger.warning(f"[browser] unload_ui 关闭隐身窗口失败: {e}")

    # 4) 关闭所有 DevTools 窗口（destroyed 钩子会自动移除列表引用）
    try:
        dt = _get_loaded_submodule("devtools")
        if dt is not None:
            for win in list(dt._open_devtools):
                try:
                    win.close()
                except RuntimeError:
                    pass
    except Exception as e:
        logger.warning(f"[browser] unload_ui 关闭 DevTools 失败: {e}")

    # 5) 清空持久 Profile 缓存（热重载后新实例重新延迟创建）
    try:
        pm = _get_loaded_submodule("profile_manager")
        if pm is not None:
            pm.reset_profiles()
    except Exception as e:
        logger.warning(f"[browser] unload_ui 重置 Profile 失败: {e}")