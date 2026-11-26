"""注册冒烟：不连宿主，只验证注册契约与单例清理。"""

import ui
from ui.hotkey import Hotkey


class FakeRegistry:
    def __init__(self):
        self.item = None

    def register_sidebar_item(self, **kwargs):
        self.item = kwargs


def test_register_sidebar_and_singleton(qapp, monkeypatch):
    monkeypatch.setattr(Hotkey, "register", lambda self: False)
    registry = FakeRegistry()
    ui.register_ui(registry)
    assert registry.item["item_id"] == "notch-chat:toggle"
    assert registry.item["plugin_name"] == "notch-chat"
    qapp.processEvents()
    assert callable(getattr(qapp, "_notch_chat_dispose", None))

    ui.register_ui(registry)
    qapp.processEvents()
    assert registry.item["label"] == "顶边快捷对话"


def test_sidebar_toggles_visibility(qapp, monkeypatch):
    monkeypatch.setattr(Hotkey, "register", lambda self: False)
    registry = FakeRegistry()
    ui.register_ui(registry)
    qapp.processEvents()
    on_click = registry.item["on_click"]
    assert on_click({}) is True
    qapp.processEvents()
    panel = [w for w in qapp.topLevelWidgets() if isinstance(w, ui.Panel)][-1]
    assert panel.isVisible() and panel.expanded
    assert on_click({}) is True
    qapp.processEvents()
    assert not panel.isVisible()
    ui._nothing = None
