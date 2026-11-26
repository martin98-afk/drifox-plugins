# -*- coding: utf-8 -*-
"""sky-glide UI 组件入口 —— 欢迎卡片「🐦 滑翔」tab

注册为欢迎卡片的一个 tab（mode_key="sky-glide"）。欢迎卡片的正文走
markdown → CodeWebViewer(innerHTML) 管线，注入的 `<script>` 不会执行，
所以这里不拼 DOM 交互，而是把整份游戏文档塞进 `<iframe srcdoc>`：
iframe 是独立文档，脚本、canvas、keydown 都跑在自己的 window 里。

渲染要点：
- srcdoc 用 html.escape(quote=True) 转义，属性值安全且能被解析回原文
- 外层用 height:0 + padding-top:56.25% 锁定 16:9（Chromium 83 无 aspect-ratio）；
  iframe 内画布另做 letterbox，容器比例失效时画面仍是横屏
- 明暗跟随 ctx["is_dark"]（主程序 Qt 主题），缺省按浅色
"""

import html
import sys

from .game_html import build_doc


def _render_game(ctx: dict = None) -> str:
    """渲染欢迎 tab 内容：16:9 iframe 包住整份游戏文档"""
    is_dark = bool(ctx.get("is_dark")) if isinstance(ctx, dict) else False
    srcdoc = html.escape(build_doc(is_dark), quote=True)

    # 全部样式内联：宿主会把外层 div 的 class/样式丢掉（实测 .sg-wrap 的
    # border-radius、padding-top 全失效，iframe 被 height:100% 撑满成方块），
    # 所以比例不靠父容器，交给 iframe 内的 fitFrame() 按自身宽度算高度。
    frame_style = (
        "display:block;width:100%;max-width:760px;margin:0 auto;height:240px;"
        "border:0;border-radius:14px;background:#101c26;"
        "box-shadow:0 6px 22px rgba(20,46,62,.14)"
    )
    hint_style = (
        "max-width:760px;margin:10px auto 0;font-size:12px;text-align:center;"
        "color:#8a8f98;letter-spacing:.02em"
    )
    return (
        f'<iframe title="滑翔鸟" scrolling="no" style="{frame_style}" srcdoc="{srcdoc}"></iframe>'
        f'<p style="{hint_style}">点一下画面拿到键盘焦点，空格起飞</p>'
    )


def register_ui(registry):
    """注册 sky-glide 的 UI 组件（欢迎卡片滑翔游戏 tab）"""
    # 清理旧子模块缓存（热重载兼容）
    prefix = "ui_plugin_sky_glide."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    registry.register_welcome_tab(
        plugin_name="sky-glide",
        mode_key="sky-glide",
        label="🐦 滑翔",
        render_func=lambda ctx: _render_game(ctx),
    )