# -*- coding: utf-8 -*-
"""magpie — 独立弹窗入口：内嵌 magpie 的网页界面（magpie web）。

为什么用独立弹窗而非浮动卡：内容页是 QWebEngineView，在 Windows 上是原生
HWND 子窗口，与主程序的非原生浮层争 z-order（项目里 workbench_panel.py 已
记过这条）。register_window 提供顶级窗口壳，宿主自行处理标题栏与布局。

前提：magpie 必须以网页模式启动（``magpie web`` / ``magpie serve --web`` /
``magpie daemon install --web``），监听 127.0.0.1:3430。装了桌面 App 不等于
开了这个端口——App 用本地 webview，不对外服务。连不上时页面给命令指引。
"""

import sys

from loguru import logger

_PLUGIN = "magpie"
_WINDOW_ID = f"{_PLUGIN}:web"


def _ctx_provider() -> dict:
    """窗口上下文：每次调用返回最新主题 token（深浅色切换后内容页重取色）。"""
    ctx: dict = {}
    try:
        from app.utils.design_tokens import Colors

        Colors.refresh()
        ctx["colors"] = {
            "text_primary": Colors.TEXT_PRIMARY,
            "text_secondary": Colors.TEXT_SECONDARY,
            "border": Colors.BORDER,
            "accent": Colors.TEXT_ACCENT,
        }
    except Exception:
        pass
    return ctx


def register_ui(registry):
    """注册 magpie 网页界面弹窗（命令 /magpie:web 由宿主自动派生）。"""
    # 热重载：清掉本插件旧子模块缓存，避免 Python 复用已卸下的 .pyc
    prefix = f"ui_plugin_{_PLUGIN.replace('-', '_')}."
    for k in [k for k in sys.modules if k.startswith(prefix)]:
        del sys.modules[k]

    from .magpie_page import MagpieWebPage

    registry.register_window(
        plugin_name=_PLUGIN,
        window_id=_WINDOW_ID,
        widget_class=MagpieWebPage,
        title="magpie",
        width=1080,
        height=720,
        min_width=640,
        min_height=420,
        context_provider=_ctx_provider,
    )
    logger.info("[magpie] 网页界面弹窗已注册")
