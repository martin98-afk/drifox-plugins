# -*- coding: utf-8 -*-
"""context-stats UI 组件入口 — 欢迎卡片「📊 用量」tab

通过 register_welcome_tab 注册为欢迎卡片的新 tab：
- mode_key="context-stats"（避开系统内置 sessions/projects/changelog）
- render_func 返回 markdown 片段（含 ```echarts 代码块），
  经欢迎卡片 markdown → CodeWebViewer(QWebEngineView) 管线渲染。

依赖主程序：
- welcome 卡片骨架需加载 echarts vendor（window.echarts 存在），
  见 DriFox app/widgets/message_card.py `_load_skeleton`（_SKELETON_CACHE_VERSION>=9）。
"""

import sys

from loguru import logger


def register_ui(registry):
    """注册 context-stats 的 UI 组件（欢迎卡片 tab）

    热重载兼容：
    清理 sys.modules 中残留的子模块缓存，确保 Python 重新从 .py 源文件编译。
    """
    # 清理旧子模块缓存（避免热重载时 Python 用旧 sys.modules 缓存）
    prefix = "ui_plugin_context_stats."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    from .render import render_welcome_tab

    registry.register_welcome_tab(
        plugin_name="context-stats",
        mode_key="context-stats",
        label="📊 用量",
        render_func=render_welcome_tab,
        priority=0,
    )
    logger.info("[context-stats] welcome tab registered")
