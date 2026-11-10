# -*- coding: utf-8 -*-
"""把卡片渲染成 PNG，用于目视检查布局/字号/层次（无需启动宿主）。

跑法：
    python plugins/meeting-notes/tests/render_preview.py
输出：同目录 preview_dark.png / preview_light.png
"""

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
UI_DIR = str(HERE.parent / "ui")

pkg = type(sys)("meeting_notes_ui")
pkg.__path__ = [UI_DIR]
sys.modules["meeting_notes_ui"] = pkg
spec = importlib.util.spec_from_file_location("meeting_notes_ui.__init__", os.path.join(UI_DIR, "__init__.py"))
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)

import importlib  # noqa: E402

store = importlib.import_module("meeting_notes_ui.store")
tmp = Path(tempfile.mkdtemp(prefix="mn_preview_"))
store.meetings_dir = lambda: tmp
store.audio_dir = lambda: tmp

from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from meeting_notes_ui.card import MeetingNotesCard  # noqa: E402

m = store.new_meeting("XingChenAGI/XingChenASR-Diarize-V3.0")
m.title = "产品评审会"
m.duration_sec = 754
m.status = "done"
m.refined_until = m.duration_sec
m.segments = [
    store.Segment(t=0.0, speaker="1", text="大家好，今天过一下三季度的进度，先请后端说。"),
    store.Segment(t=14.2, speaker="2", text="接口联调完了，压测还没开始，本周五之前能给结果。"),
    store.Segment(t=32.8, speaker="1", text="压测的指标定一下，主要看 P99 和内存峰值。"),
    store.Segment(t=48.0, speaker="3", text="我这边补一下监控看板，跟压测同步上线。"),
    store.Segment(t=63.5, speaker="2", text="那我把压测脚本和监控指标对齐，明天发群里。"),
]
m.speaker_names = {"2": "张三", "3": "李四"}
m.summary_md = (
    "## 一句话概要\n三季度进度对齐，压测与监控看板本周内落地。\n\n"
    "## 关键讨论\n- 后端接口联调完成，压测未开始，周五前出结果\n"
    "- 压测核心指标定为 P99 延迟与内存峰值\n- 监控看板与压测同步上线\n\n"
    "## 决议\n- 压测指标按 P99 + 内存峰值执行\n\n"
    "## 待办\n- 压测结果 —— 张三 —— 本周五\n- 监控看板 —— 李四 —— 与压测同步\n\n"
    "## 风险与分歧\n- 压测时间紧，若指标不达标需要二次排期\n"
)
store.save(m)

m2 = store.new_meeting("XingChenAGI/XingChenASR-Diarize-V3.0")
m2.title = "周会"
m2.duration_sec = 122
m2.status = "done"
store.save(m2)


def shoot(dark: bool, name: str) -> None:
    card = MeetingNotesCard()
    ctx = {
        "colors": {},
        "is_dark": dark,
        "font_family": "Microsoft YaHei",
        "font_size": 14,
    }
    card.set_context_provider(lambda: ctx)
    card.show_card()
    card._reload_list()
    card._on_item_clicked(m.id)
    card._switch_tab(1)
    card.resize(1240, 760)
    card.show()
    app.processEvents()
    card.grab().save(str(HERE / name))
    print("saved", name, card.size().width(), "x", card.size().height())
    card.deleteLater()


shoot(True, "preview_dark.png")
shoot(False, "preview_light.png")
