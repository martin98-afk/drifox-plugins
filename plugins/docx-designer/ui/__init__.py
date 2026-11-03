# -*- coding: utf-8 -*-
"""docx-designer UI 组件入口

注册浮动卡片「文档设计」（/docx-designer 命令由 register_floating_card 自动注册）。
热重载语义与 browser 插件一致：
1. 清理 sys.modules 中残留的 ui_plugin_docx_designer.* 子模块缓存
2. 清理 function handlers 中残留的旧引用
3. 注册浮动卡片
"""

import sys

from loguru import logger


def register_ui(registry):
    # 0) 安装 docx 文件拦截：系统打开 .docx 默认进文档设计预览
    try:
        from .external_open import install_docx_redirect

        install_docx_redirect()
    except Exception:
        logger.exception("[docx-designer] docx 文件拦截安装失败（不影响其余功能）")

    # 1) 清理旧子模块缓存（热重载防旧 .pyc）
    prefix = "ui_plugin_docx_designer."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    # 2) 清理 function handlers 残留
    try:
        from app.core.commands.builtin_commands import FunctionCommandHandlers

        FunctionCommandHandlers._handlers.pop("docx-designer", None)
    except Exception:
        pass

    # 3) 注册浮动卡片
    from .docx_window import DocxWindowCard

    registry.register_floating_card(
        plugin_name="docx-designer",
        card_id="docx-designer",
        widget_class=DocxWindowCard,
        container="right",
        title="文档设计",
        default_visible=False,
    )
    logger.info("[docx-designer] UI components registered")


def unload_ui(registry):
    """无外部资源需手动释放；窗口随 registry 清理。"""
