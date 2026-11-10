# -*- coding: utf-8 -*-
"""确认弹窗无头冒烟：构造 + 尺寸 + 按钮文案，不 exec_。

跑法：python plugins/meeting-notes/tests/smoke_dialogs.py
"""

import importlib.util
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

UI_DIR = str(Path(__file__).resolve().parent.parent / "ui")

pkg = type(sys)("meeting_notes_ui")
pkg.__path__ = [UI_DIR]
sys.modules["meeting_notes_ui"] = pkg
spec = importlib.util.spec_from_file_location("meeting_notes_ui.__init__", os.path.join(UI_DIR, "__init__.py"))
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)

from importlib import import_module  # noqa: E402

from PyQt5.QtWidgets import QApplication, QPushButton, QWidget  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
host = QWidget()

theme_mod = import_module("meeting_notes_ui.theme")
dialogs = import_module("meeting_notes_ui.dialogs")

theme = theme_mod.Theme({"colors": {}, "is_dark": True, "font_family": "Microsoft YaHei", "font_size": 14})
dlg = dialogs.ConfirmDialog(host, theme, "删除会议", "确定删除「周会」？录音与纪要会一并删除。", "删除")
buttons = dlg.widget.findChildren(QPushButton)
labels = [b.text() for b in buttons]
print("按钮:", labels)
print("卡片尺寸:", dlg.widget.width(), "x", dlg.widget.height())
assert labels == ["取消", "删除"], labels
assert dlg.widget.width() == 420
assert dlg.widget.height() > 80, dlg.widget.height()
dlg.deleteLater()
print("SMOKE DIALOG OK")
