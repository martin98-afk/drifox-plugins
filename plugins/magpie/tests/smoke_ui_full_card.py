# -*- coding: utf-8 -*-
"""UI 注册桩测试：验证 full 容器注册、命令名 /magpie:web 与自愈侧栏回调。

跑法（项目 venv）：
    python plugins/magpie/tests/smoke_ui_full_card.py
"""
import importlib.util
import sys
import types

# 桩掉宿主依赖（loguru 仅日志、magpie_page 延迟 import 不触发）
sys.modules.setdefault("loguru", types.SimpleNamespace(logger=types.SimpleNamespace(debug=lambda *a, **k: None, info=lambda *a, **k: None)))

# 以包形态加载（magpie_page 是相对 import，需要父包上下文）
pkg = types.ModuleType("magpie_ui")
pkg.__path__ = ["plugins/magpie/ui"]
sys.modules["magpie_ui"] = pkg
spec = importlib.util.spec_from_file_location("magpie_ui.__init__", "plugins/magpie/ui/__init__.py")
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)

registered = {}
sidebar_registered = {}


class FakeRegistry:
    def register_floating_card(self, **kw):
        registered.update(kw)

    def register_sidebar_item(self, **kw):
        sidebar_registered.update(kw)

    def _resolve_global_host(self):
        return None  # 假死探测路径：无 host → 跳过自愈分支

    def toggle_floating_card(self, card_id):
        sidebar_registered.setdefault("toggled", []).append(card_id)


ui.register_ui(FakeRegistry())

assert registered["plugin_name"] == "magpie"
assert registered["card_id"] == "magpie:web"
assert registered["container"] == "full"
assert registered["default_visible"] is False
assert callable(registered["context_provider"])
meta = registered["metadata"]
assert meta["full_card"] is True
assert "hide_sidebar" not in meta  # 入口改侧栏项，卡片可进侧栏列表
assert "primary_entry" not in meta  # 入口侧栏项改手写注册（假死自愈回调）
assert registered["widget_class"].__name__ == "MagpieWebPage"

# 侧栏项注册：card_id 带 ":" 保命令名；group=custom 进「自定义插件」折叠区
assert sidebar_registered["plugin_name"] == "magpie"
assert sidebar_registered["item_id"] == "magpie:web"
assert sidebar_registered["label"] == "magpie"
assert sidebar_registered["group"] == "custom"
assert sidebar_registered["card_id"] == "magpie:web"
assert callable(sidebar_registered["on_click"])
sidebar_registered["on_click"]({})
assert sidebar_registered["toggled"] == ["magpie:web"]
print("UI full-card + self-heal sidebar item OK:", registered["card_id"], "/", registered["container"])
