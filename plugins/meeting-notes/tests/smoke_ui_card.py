# -*- coding: utf-8 -*-
"""无头冒烟：注册参数 + 卡片实例化 + 主题切换 + 渲染一场假会议。

跑法（项目 venv，需 Qt）：
    set QT_QPA_PLATFORM=offscreen && python plugins/meeting-notes/tests/smoke_ui_card.py

它不碰麦克风与网络，只验证「装进宿主后卡片能不能活」：导入错误、控件不存在、
布局崩溃、主题切换异常都会在这里炸出来。
"""

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

UI_DIR = str(Path(__file__).resolve().parent.parent / "ui")

# 以包形态加载（card.py 里有大量相对 import）
pkg = type(sys)("meeting_notes_ui")
pkg.__path__ = [UI_DIR]
sys.modules["meeting_notes_ui"] = pkg
spec = importlib.util.spec_from_file_location("meeting_notes_ui.__init__", os.path.join(UI_DIR, "__init__.py"))
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)

# 数据目录指到临时目录，别污染真实 plugin_data
import importlib  # noqa: E402

store = importlib.import_module("meeting_notes_ui.store")
tmp = Path(tempfile.mkdtemp(prefix="mn_smoke_"))
store.data_root = lambda: tmp
store._migrated = True


class FakeRegistry:
    def __init__(self):
        self.card = {}

    def register_floating_card(self, **kw):
        self.card.update(kw)


reg = FakeRegistry()
ui.register_ui(reg)
assert reg.card["plugin_name"] == "meeting-notes"
assert reg.card["container"] == "full"
assert reg.card["metadata"]["full_card"] is True
assert reg.card["metadata"]["primary_entry"]["kind"] == "titlebar"
print("注册参数 OK:", reg.card["card_id"], reg.card["container"], reg.card["metadata"]["primary_entry"])

from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

Card = reg.card["widget_class"]
card = Card()
ctx_dark = {
    "colors": {},
    "is_dark": True,
    "font_family": "Microsoft YaHei",
    "font_size": 14,
}
card.set_context_provider(lambda: ctx_dark)
card.show_card()
card.resize(1180, 720)
app.processEvents()
print("卡片实例化 + show_card OK:", card.size().width(), "x", card.size().height())

# 造一场会议并渲染
m = store.new_meeting("XingChenAGI/XingChenASR-Diarize-V3.0")
m.title = "冒烟会议"
m.duration_sec = 95
m.status = "done"
m.segments = [
    store.Segment(t=0.0, speaker="1", text="大家好，今天过一下进度。"),
    store.Segment(t=6.4, speaker="2", text="我先说后端，接口已经联调完，还剩压测。"),
    store.Segment(t=21.0, speaker="1", text="压测什么时候能出结果？"),
]
m.speaker_names = {"2": "张三"}
m.summary_md = "## 一句话概要\n过进度。\n\n## 待办\n- 压测 —— 张三 —— 本周五\n"
store.save(m)

card._reload_list()
card._on_item_clicked(m.id)
app.processEvents()
rows = card._find_rows()
assert len(rows) == 3, f"转写行数应为 3，实际 {len(rows)}"
assert card._items.get(m.id) is not None
print("列表 + 转写渲染 OK:", len(rows), "行")

card._switch_tab(1)
app.processEvents()
assert card._stack.currentIndex() == 1
plain = card._browser.toPlainText()
assert "待办" in plain, plain[:200]
print("纪要 Markdown 渲染 OK:", plain.replace("\n", " ")[:60])

# 浅色主题切换
ctx_light = dict(ctx_dark, is_dark=False)
card.set_context_provider(lambda: ctx_light)
card.apply_theme()
app.processEvents()
print("浅色主题切换 OK")

# 空状态
card._meeting = None
card._render_current()
app.processEvents()
print("空状态渲染 OK")

card.deleteLater()
print("SMOKE OK")
