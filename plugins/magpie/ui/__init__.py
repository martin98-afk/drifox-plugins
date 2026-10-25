# -*- coding: utf-8 -*-
"""magpie — full 容器工作页：内嵌 magpie 的网页界面（magpie web）。

容器选型：内容页是 QWebEngineView，Windows 上是原生 HWND 子窗口，与主程序
非原生浮层争 z-order（workbench_panel.py 记过这条）。full 容器走主窗口
_content_stack 整页替换（QStackedWidget 互斥显示），webview 独占自己的页，
不与浮层同屏重叠，标题栏 tab 在 stack 之外不受影响；此前为此选的独立弹窗
已改成本形态。入口为主窗口顶部常驻 tab「magpie」（点击开合），命令
/magpie:web 同义。

前提：magpie 必须以网页模式启动（``magpie web`` / ``magpie serve --web`` /
``magpie daemon install --web``），监听 127.0.0.1:3430。装了桌面 App 不等于
开了这个端口——App 用本地 webview，不对外服务。连不上时页面给命令指引。
"""

import sys

from loguru import logger

_PLUGIN = "magpie"
# card_id 自带 ":" → 宿主直接用作命令名，保持与独立弹窗时代的 /magpie:web 一致
_CARD_ID = f"{_PLUGIN}:web"


def _ctx_provider() -> dict:
    """卡片上下文：每次调用返回最新主题 token（深浅色切换后内容页重取色）。"""
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
    """注册 magpie 网页工作页（标题栏常驻 tab 由 primary_entry 派生）。"""
    # 热重载：清掉本插件旧子模块缓存，避免 Python 复用已卸下的 .pyc
    prefix = f"ui_plugin_{_PLUGIN.replace('-', '_')}."
    for k in [k for k in sys.modules if k.startswith(prefix)]:
        del sys.modules[k]

    from .magpie_page import MagpieWebPage

    registry.register_floating_card(
        plugin_name=_PLUGIN,
        card_id=_CARD_ID,
        widget_class=MagpieWebPage,
        container="full",
        title="magpie",
        default_visible=False,
        context_provider=_ctx_provider,
        metadata={
            # 全窗口页（与设置卡同款：可被标题栏 full tab 接管，带 × 关闭钮）
            "full_card": True,
            # 入口只有标题栏「magpie」常驻 tab，侧边栏不重复列出
            "hide_sidebar": True,
            # 一处注册、多处分发：框架自动派生 tab（已可见忽略、否则唤出本卡）
            "primary_entry": {"kind": "titlebar", "label": "magpie"},
        },
    )
    logger.info("[magpie] 网页界面工作页已注册（full + titlebar tab）")
