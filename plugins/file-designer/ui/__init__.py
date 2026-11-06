# -*- coding: utf-8 -*-
"""file-designer UI 组件入口

注册浮动卡片「文件设计」（/file-designer 命令由 register_floating_card 自动注册）。
热重载语义与 browser 插件一致：
1. 清理 sys.modules 中残留的 ui_plugin_file_designer.* 子模块缓存
2. 清理 function handlers 中残留的旧引用
3. 注册浮动卡片
"""

import sys
from pathlib import Path

from loguru import logger

from .formats import migrate_data_dir

def register_ui(registry):
    # 0) 旧插件数据迁移（picks 截图 + 标注 JSON 整目录复制，只跑一次）
    try:
        migrate_data_dir()
    except Exception:
        logger.exception("[file-designer] 旧数据迁移失败（不影响其余功能）")

    # 1) 安装文件拦截：系统打开受支持格式默认进文件设计预览
    try:
        from .external_open import install_redirect

        install_redirect()
    except Exception:
        logger.exception("[file-designer] 文件拦截安装失败（不影响其余功能）")

    # 2) 清理旧子模块缓存（热重载防旧 .pyc）
    prefix = "ui_plugin_file_designer."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    # 3) 清理 function handlers 残留
    try:
        from app.core.commands.builtin_commands import FunctionCommandHandlers

        FunctionCommandHandlers._handlers.pop("file-designer", None)
    except Exception:
        pass

    # 4) 注册浮动卡片
    from .docx_window import DocxWindowCard

    registry.register_floating_card(
        plugin_name="file-designer",
        card_id="file-designer",
        widget_class=DocxWindowCard,
        container="right",
        title="文件设计",
        default_visible=False,
    )
    logger.info("[file-designer] UI components registered")

def unload_ui(registry):
    """无外部资源需手动释放；窗口随 registry 清理。"""
