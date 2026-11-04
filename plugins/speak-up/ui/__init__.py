# -*- coding: utf-8 -*-
"""speak-up UI 组件入口 — 注册浮动卡与独立设置大 tab。

注意：宿主 AST 安全网（`app/plugins/loaders/_ast_guard.py`）要求本文件**本体**
定义 `register_ui` 函数（扫的是 FunctionDef，`from x import register_ui` 不算），
故这里写成薄包装，实体在同目录 `speakup_ui.py`。
"""

import sys
from pathlib import Path

# 插件根加入 sys.path（自包含：core 以 speakup_core.* 导入）
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))


def register_ui(registry):
    """注册浮动卡与设置页（实体见 speakup_ui.register_ui）。"""
    from .speakup_ui import register_ui as _impl

    return _impl(registry)


def unload_ui(registry):
    """卸载回调（实体见 speakup_ui.unload_ui）。"""
    from .speakup_ui import unload_ui as _impl

    return _impl(registry)
