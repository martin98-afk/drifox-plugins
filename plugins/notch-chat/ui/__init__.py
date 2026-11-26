"""注册侧栏入口，创建独立于主窗口的顶边小窗。"""

import sys

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication

from .hotkey import Hotkey
from .panel import Panel

PLUGIN = "notch-chat"
ITEM = "notch-chat:toggle"


def register_ui(registry):
    if sys.platform != "darwin":
        return
    app = QApplication.instance()
    if app is None:
        return
    previous = getattr(app, "_notch_chat_dispose", None)
    if previous is not None:
        previous()
    panel = None
    key = None

    def create():
        from app.plugins.sdk import pool_for

        caps = pool_for(plugin=PLUGIN, surface="ui")
        if caps is None or "engine.session" not in caps:
            raise RuntimeError("宿主不支持独立对话")
        return caps["engine.session"](
            PLUGIN, hook_policy="none", permission_strategy="auto_allow"
        )

    def open_panel():
        nonlocal panel, key
        if panel is None:
            try:
                from qfluentwidgets import isDarkTheme
            except ImportError:
                isDarkTheme = lambda: False
            panel = Panel(create, dark=isDarkTheme())
            key = Hotkey(panel)
            key.pressed.connect(panel.toggle, Qt.QueuedConnection)
            key_ok = key.register()
            panel.hotkey_hint = (
                f"Esc 收起   ·   {key.label} 呼出"
                if key_ok else f"Esc 收起   ·   热键不可用（{key.reason or '系统拒绝'}）"
            )
            panel.set_state(panel.state)
            app.paletteChanged.connect(lambda _palette: panel and panel.set_theme(isDarkTheme()))
        return panel

    def on_sidebar(_context):
        page = open_panel()
        if page.isVisible():
            page.hide_panel()
        else:
            page.expand()
        return True

    def dispose():
        nonlocal panel, key
        if key is not None:
            key.close()
            key = None
        if panel is not None:
            panel.chat.shutdown()
            panel.close()
            panel.deleteLater()
            panel = None
        if getattr(app, "_notch_chat_dispose", None) is dispose:
            app._notch_chat_dispose = None
        try:
            app.aboutToQuit.disconnect(dispose)
        except TypeError:
            pass

    app._notch_chat_dispose = dispose
    app.aboutToQuit.connect(dispose)
    registry.register_sidebar_item(
        plugin_name=PLUGIN, item_id=ITEM, label="顶边快捷对话",
        group="custom", default_visible=True, on_click=on_sidebar,
    )
    QTimer.singleShot(0, open_panel)
