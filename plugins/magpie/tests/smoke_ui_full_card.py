# -*- coding: utf-8 -*-
"""UI 注册桩测试：验证 full 容器注册、命令名 /magpie:web 与自愈 tab 回调。

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
tab_registered = {}


class FakeRegistry:
    def register_floating_card(self, **kw):
        registered.update(kw)

    def register_titlebar_tab(self, **kw):
        tab_registered.update(kw)

    def _resolve_global_host(self):
        return None  # 假死探测路径：无 host → 跳过自愈分支

    def toggle_floating_card(self, card_id):
        tab_registered.setdefault("toggled", []).append(card_id)


ui.register_ui(FakeRegistry())

assert registered["plugin_name"] == "magpie"
assert registered["card_id"] == "magpie:web"
assert registered["container"] == "full"
assert registered["default_visible"] is False
assert callable(registered["context_provider"])
meta = registered["metadata"]
assert meta["full_card"] is True
assert meta["hide_sidebar"] is True
assert "primary_entry" not in meta  # 入口 tab 改手写注册（假死自愈回调）
assert registered["widget_class"].__name__ == "MagpieWebPage"

# tab 注册：card_id 带 ":" 保命令名；回调可调用且触发 toggle
assert tab_registered["plugin_name"] == "magpie"
assert tab_registered["tab_id"] == "magpie:web"
assert tab_registered["label"] == "magpie"
assert callable(tab_registered["on_click"])
tab_registered["on_click"]()
assert tab_registered["toggled"] == ["magpie:web"]
print("UI full-card + self-heal tab OK:", registered["card_id"], "/", registered["container"])
