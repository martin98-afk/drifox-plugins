# -*- coding: utf-8 -*-
"""团队模式崩溃回归复现脚本（供 test_smoke 子进程调用）

背景：_SessionItem.paintEvent 用 QPainter.drawLine 绘制树线，在 QSS 样式化
widget 树 + QScrollArea 环境中触发 Qt 5.15 崩溃（0xc0000409 / 0xc00000fd）。
已改为子控件 QFrame 实现。本脚本验证团队会话渲染 + 事件循环不再崩溃。

正常退出码 0；崩溃时退出码为 0xC0000409（-1073740791）。
"""

import datetime
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ui"))
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([sys.argv[0]])

import session_tree as st  # noqa: E402

NOW = datetime.datetime.now()


def ts(days=0, hours=0):
    return (NOW - datetime.timedelta(days=days, hours=hours)).strftime("%Y-%m-%d %H:%M:%S")


SESSIONS = [
    {"session_id": "t1", "title": "团队会话A", "last_time": ts(0, 1), "preview": "p",
     "project": "Demo", "team_run_id": "run-1", "team_name": "团队A", "agent_name": "leader"},
    {"session_id": "t2", "title": "成员1", "last_time": ts(0, 2), "preview": "",
     "project": "Demo", "team_run_id": "run-1", "team_name": "团队A", "agent_name": "build"},
]


class _FakeHM:
    def get_history_list(self, project=None):
        return [dict(s) for s in SESSIONS]


class _FakeMW:
    _current_project = "Demo"
    _current_session_id = "n1"
    history_manager = _FakeHM()


card = st.SessionTreeCard()
card.set_context_provider(lambda: {"main_widget": _FakeMW(), "colors": {}, "is_dark": True})
card.show()
card.resize(280, 600)
card._refresh()
card._refresh()
for _ in range(5):
    app.processEvents()
# 折叠团队再展开（树线显隐路径）
card._on_team_toggled("run-1")
app.processEvents()
card._on_team_toggled("run-1")
app.processEvents()
print("TEAM MODE OK")
