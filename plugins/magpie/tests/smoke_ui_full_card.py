# -*- coding: utf-8 -*-
"""UI 注册桩测试：验证 register_ui 以 full 容器注册且命令名保持 /magpie:web。

跑法（项目 venv）：
    python plugins/magpie/tests/smoke_ui_full_card.py
"""
import importlib.util
import sys
import types

# 桩掉宿主依赖（loguru 仅日志、magpie_page 延迟 import 不触发）
sys.modules.setdefault("loguru", types.SimpleNamespace(logger=types.SimpleNamespace(info=lambda *a, **k: None)))

# 以包形态加载（magpie_page 是相对 import，需要父包上下文）
pkg = types.ModuleType("magpie_ui")
pkg.__path__ = ["plugins/magpie/ui"]
sys.modules["magpie_ui"] = pkg
spec = importlib.util.spec_from_file_location("magpie_ui.__init__", "plugins/magpie/ui/__init__.py")
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)

registered = {}


class FakeRegistry:
    def register_floating_card(self, **kw):
        registered.update(kw)


ui.register_ui(FakeRegistry())

assert registered["plugin_name"] == "magpie"
assert registered["card_id"] == "magpie:web"
assert registered["container"] == "full"
assert registered["default_visible"] is False
assert callable(registered["context_provider"])
meta = registered["metadata"]
assert meta["full_card"] is True
assert meta["hide_sidebar"] is True
assert meta["primary_entry"] == {"kind": "titlebar", "label": "magpie"}
assert registered["widget_class"].__name__ == "MagpieWebPage"
print("UI full-card registration OK:", registered["card_id"], "/", registered["container"])
