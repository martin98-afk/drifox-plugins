# -*- coding: utf-8 -*-
"""session-tree 真实注册链路验证：UIPluginRegistry + plugin.json 加载"""
import importlib.util
import json
import sys
from pathlib import Path

PLUGIN_DIR = Path.home() / ".drifox" / "plugins" / "session-tree"

# 1. manifest 校验
manifest = json.loads((PLUGIN_DIR / ".drifox-plugin" / "plugin.json").read_text(encoding="utf-8"))
assert manifest["name"] == "session-tree"
assert manifest["components"]["ui"] is True
assert manifest["name"] == PLUGIN_DIR.name, "目录名与 name 不一致"
print("[1] manifest OK:", manifest["version"])

# 2. 通过真实 UIPluginRegistry 注册（模拟 plugin_manager 加载 ui 组件）
from app.plugins.registries.ui_plugin_registry import UIPluginRegistry

reg = UIPluginRegistry()
ui_init = PLUGIN_DIR / "ui" / "__init__.py"
spec = importlib.util.spec_from_file_location("ui_plugin_session_tree_reg", ui_init)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
mod.register_ui(reg)
cards = reg.get_floating_cards()
info = cards.get("session-tree")
assert info is not None, "card 未注册"
assert info.container == "left"
assert info.plugin_name == "session-tree"
print("[2] register_ui OK -> card_id=session-tree container=left")

# 3. 上下文构建（模拟窗口 provider 返回结构）
ctx = reg._build_card_context(info)
assert "plugin_name" in ctx and "card_id" in ctx
print("[3] _build_card_context OK:", sorted(ctx.keys()))
print("ALL PASS")
