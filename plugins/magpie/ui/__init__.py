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
    """注册 magpie 网页工作页（标题栏 tab 手写回调：假死自愈 + 开合语义）。

    为什么不用 primary_entry 声明式派生（show-only）：webview 首次构造触发
    父链原生化，TOP 覆盖层容器短暂不可见，而 CardManager 状态层已置可见——
    形成「状态可见、视觉不可见」死锁，show-only 语义下后续点击全被忽略
    （实测连点无反应）。手写回调每次点击先检测该假死态（状态可见但容器
    不可见 → 清状态），再走 toggle：假死自愈，正常态等于开合（点显示中的
    页签即关闭，与 × 等价）。
    """
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
            # 入口 tab 由下方手写 register_titlebar_tab 承接（假死自愈回调）
        },
    )

    def _on_tab_click():
        # 假死自愈：状态层可见但覆盖层容器不可见（webview 原生化副作用）
        # → hide_card 清掉假状态，让下方 toggle 必走 show 分支
        try:
            host = registry._resolve_global_host()
            if host is not None:
                cm = getattr(host, "_card_manager", None)
                wid = getattr(host, "_window_id", None)
                cont = getattr(host, "_top_card_container", None)
                if cm is not None and wid and cont is not None:
                    if cm.is_card_visible(_CARD_ID, wid) and not cont.isVisible():
                        logger.debug("[magpie] 检测到假可见态（容器不可见），先清状态")
                        cm.hide_card(_CARD_ID, wid)
        except Exception as e:  # noqa: BLE001 — 自愈探测失败不影响正常 toggle
            logger.debug(f"[magpie] 假死探测跳过: {e}")
        registry.toggle_floating_card(_CARD_ID)

    registry.register_titlebar_tab(
        plugin_name=_PLUGIN,
        tab_id=_CARD_ID,
        label="magpie",
        card_id=_CARD_ID,
        on_click=_on_tab_click,
    )
    logger.info("[magpie] 网页界面工作页已注册（full + 自愈 tab 回调）")
