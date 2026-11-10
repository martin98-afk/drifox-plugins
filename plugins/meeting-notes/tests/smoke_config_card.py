# -*- coding: utf-8 -*-
"""设置卡无头冒烟：跑到能实例化、控件回显正常即通过（不需要宿主）。

跑法：python plugins/meeting-notes/tests/smoke_config_card.py
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

from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

cc = import_module("meeting_notes_ui.config_card")
card = cc._MeetingNotesConfigCard()
print("配置卡实例化 OK")
print("识别模型项数:", card._asr_model.count())
print("纪要模型项数:", card._summary_model.count(), "首项:", card._summary_model.itemText(0))
print("提示词长度:", len(card._prompt.toPlainText()))
print("切片时长:", card._chunk.value(), "保留录音:", card._keep_audio.isChecked())
card.deleteLater()
print("SMOKE CONFIG OK")
