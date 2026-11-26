# -*- coding: utf-8 -*-
"""sky-glide UI 组件入口 —— 欢迎卡片「🐦 滑翔」tab

注册为欢迎卡片的一个 tab（mode_key="sky-glide"）。欢迎卡片的正文走
markdown → CodeWebViewer(innerHTML) 管线，注入的 `<script>` 不会执行，
所以这里不拼 DOM 交互，而是把整份游戏文档塞进 `<iframe srcdoc>`：
iframe 是独立文档，脚本、canvas、keydown 都跑在自己的 window 里。

渲染要点：
- srcdoc 用 html.escape(quote=True) 转义，属性值安全且能被解析回原文
- 外层用 padding-top:56.25% 撑 16:9（Chromium 83 不支持 aspect-ratio）
- 明暗跟随 ctx["is_dark"]（主程序 Qt 主题），缺省按浅色
"""

import html
import sys

from .game_html import build_doc


def _render_game(ctx: dict = None) -> str:
    """渲染欢迎 tab 内容：16:9 iframe 包住整份游戏文档"""
    is_dark = bool(ctx.get("is_dark")) if isinstance(ctx, dict) else False
    srcdoc = html.escape(build_doc(is_dark), quote=True)

    return f"""<div class="sg-wrap">
  <iframe class="sg-frame" title="滑翔鸟" scrolling="no" srcdoc="{srcdoc}"></iframe>
</div>
<p class="sg-hint">点一下画面拿到键盘焦点，空格起飞</p>
<style>
.sg-wrap {{
  position: relative; width: 100%; max-width: 760px; margin: 0 auto;
  padding-top: 56.25%; border-radius: 14px; overflow: hidden;
  box-shadow: 0 6px 22px rgba(20, 46, 62, 0.14);
}}
.sg-frame {{
  position: absolute; left: 0; top: 0; width: 100%; height: 100%;
  border: 0; display: block; background: #101c26;
}}
.sg-hint {{
  max-width: 760px; margin: 10px auto 0; font-size: 12px;
  color: var(--text-muted, #8a8f98); text-align: center; letter-spacing: 0.02em;
}}
</style>
"""


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