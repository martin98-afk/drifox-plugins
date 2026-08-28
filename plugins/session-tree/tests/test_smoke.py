# -*- coding: utf-8 -*-
"""session-tree P1 冒烟测试（stdlib unittest + PySide6 offscreen）

覆盖：
- 时间分组逻辑（_group_of / _time_text / _parse_ts）
- register_ui 注册（mock registry 断言参数）
- SessionTreeCard 实例化 + 数据流（mock main_widget + provider）：
  列表重建、当前项高亮、组标题、右键操作数据层调用

运行：cd C:/Users/black/.drifox/plugins/session-tree && python -m unittest tests.test_smoke -v
"""

import importlib.util
import os
import sys
import unittest
from datetime import datetime, timedelta

UI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui")
sys.path.insert(0, UI_DIR)

_SPEC = importlib.util.spec_from_file_location("ui_plugin_session_tree", os.path.join(UI_DIR, "__init__.py"))
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["ui_plugin_session_tree"] = _MOD
_SPEC.loader.exec_module(_MOD)

import ui_plugin_session_tree.session_tree as st  # noqa: E402

_APP = None


def _ensure_qapp():
    """offscreen QApplication（保持模块级引用，避免 GC 崩溃）"""
    global _APP
    if _APP is None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        _APP = QApplication.instance() or QApplication([sys.argv[0]])
        _APP.setAttribute(Qt.AA_Use96Dpi, True)
    return _APP


# ── Mock 数据 ──

def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


NOW = datetime.now()
SESSIONS = [
    {"session_id": "s-today", "title": "今日会话", "last_time": _ts(NOW - timedelta(minutes=5)),
     "preview": "今天的一条预览", "project": "Demo", "message_count": 5},
    {"session_id": "s-yest", "title": "昨日会话", "last_time": _ts(NOW - timedelta(days=1, hours=1)),
     "preview": "", "project": "Demo", "message_count": 3},
    {"session_id": "s-3d", "title": "三天前会话", "last_time": _ts(NOW - timedelta(days=3)),
     "preview": "三天前预览", "project": "Demo", "message_count": 8},
    {"session_id": "s-20d", "title": "二十天前", "last_time": _ts(NOW - timedelta(days=20)),
     "preview": "", "project": "Demo", "message_count": 1},
    {"session_id": "s-old", "title": "老会话", "last_time": _ts(NOW - timedelta(days=100)),
     "preview": "", "project": "Demo", "message_count": 2},
]


class _FakeHistoryManager:
    def __init__(self, sessions):
        self._sessions = sessions

    def get_history_list(self, project=None):
        return [dict(s) for s in self._sessions if s["project"] == project or project is None]

    def find_index_by_session_id(self, sid):
        for i, s in enumerate(self._sessions):
            if s["session_id"] == sid:
                return i
        return None

    def get_session_by_session_id(self, sid):
        for s in self._sessions:
            if s["session_id"] == sid:
                return dict(s)
        return None

    def update_session_title(self, index, title):
        self._sessions[index]["title"] = title

    def set_user_edited_title(self, index, edited):
        pass

    def remove_session(self, session_id, release_messages_only=True):
        for i, s in enumerate(self._sessions):
            if s["session_id"] == session_id:
                if release_messages_only:
                    s["messages"] = []
                else:
                    self._sessions.pop(i)
                return True
        return False

    def archive_history(self, index):
        if 0 <= index < len(self._sessions):
            self._sessions.pop(index)
            return True
        return False


class _FakeStore:
    def delete_session(self, sid):
        return True

    def update_session_title(self, sid, title):
        return True


class _FakeMainWidget:
    def __init__(self, sessions):
        self.history_manager = _FakeHistoryManager(sessions)
        self.session_store = _FakeStore()
        self._current_project = "Demo"
        self._current_session_id = "s-today"
        self._notify_calls = 0
        self._switched = None
        self._new_calls = 0

    def _switch_to_session_by_id(self, sid):
        self._switched = sid
        self._current_session_id = sid

    def _create_new_session(self):
        self._new_calls += 1
        self._current_session_id = "s-new"

    def _notify_history_data_changed(self):
        self._notify_calls += 1


class TestTimeGrouping(unittest.TestCase):
    """时间分组与格式化逻辑（纯函数，固定时间构造）"""

    NOW = datetime(2026, 8, 25, 12, 0, 0)

    def test_group_boundaries(self):
        now = self.NOW
        self.assertEqual(st._group_of("2026-08-25 10:00:00", now), "today")
        self.assertEqual(st._group_of("2026-08-25 23:59:59", now), "today")
        self.assertEqual(st._group_of("2026-08-24 00:00:00", now), "yesterday")
        self.assertEqual(st._group_of("2026-08-24 23:59:59", now), "yesterday")
        self.assertEqual(st._group_of("2026-08-23 12:00:00", now), "7d")
        self.assertEqual(st._group_of("2026-08-19 12:00:00", now), "7d")
        self.assertEqual(st._group_of("2026-08-18 12:00:00", now), "30d")
        self.assertEqual(st._group_of("2026-07-26 12:00:00", now), "30d")
        self.assertEqual(st._group_of("2026-07-26 11:59:59", now), "30d")  # 正好 30 天整 → 30d
        self.assertEqual(st._group_of("2026-07-25 12:00:00", now), "older")  # 31 天 → older
        self.assertEqual(st._group_of("", now), "older")
        self.assertEqual(st._group_of("bad-format", now), "older")

    def test_time_text(self):
        now = self.NOW
        self.assertEqual(st._time_text("2026-08-25 10:30:00", "today"), "10:30")
        self.assertEqual(st._time_text("2026-08-24 12:00:00", "yesterday"), "昨天")
        self.assertEqual(st._time_text("2026-08-22 12:00:00", "7d"), "3天前")
        self.assertEqual(st._time_text("2026-07-01 12:00:00", "older"), "07-01")

    def test_preview_truncate(self):
        long_preview = "x" * 100
        out = st._preview_text({"preview": long_preview})
        self.assertEqual(len(out), 47)  # 46 + …
        self.assertEqual(st._preview_text({"preview": ""}), "")
        self.assertEqual(st._preview_text({"preview": None}), "")


class TestRegisterUI(unittest.TestCase):
    """register_ui 注册参数"""

    def test_registration(self):
        calls = {}

        class _FakeRegistry:
            def register_floating_card(self, **kw):
                calls.update(kw)

        _MOD.register_ui(_FakeRegistry())
        # register_ui 内部热重载 stale 清理会重新加载子模块 → 重新取最新类引用
        import importlib

        st_latest = importlib.import_module("ui_plugin_session_tree.session_tree")
        self.assertEqual(calls["plugin_name"], "session-tree")
        self.assertEqual(calls["card_id"], "session-tree")
        self.assertEqual(calls["container"], "left")
        self.assertTrue(calls["default_visible"])
        self.assertTrue(issubclass(calls["widget_class"], st_latest.SessionTreeCard))


class TestCardDataFlow(unittest.TestCase):
    """卡片实例化 + 数据流（offscreen Qt）"""

    @classmethod
    def setUpClass(cls):
        _ensure_qapp()

    def _make_card(self):
        mw = _FakeMainWidget([dict(s) for s in SESSIONS])
        card = st.SessionTreeCard()
        card.set_context_provider(lambda: {"main_widget": mw, "colors": {}, "is_dark": True})
        return card, mw

    def test_rebuild_groups_and_highlight(self):
        card, mw = self._make_card()
        card._refresh()

        # 当前项高亮
        self.assertEqual(card._current_sid, "s-today")
        self.assertTrue(card._items["s-today"].property("current"))
        self.assertFalse(card._items["s-yest"].property("current"))
        # 5 个会话全部渲染
        self.assertEqual(set(card._items.keys()),
                         {"s-today", "s-yest", "s-3d", "s-20d", "s-old"})
        # 分组标题数量：5 个会话分属 5 组（用户版带折叠箭头前缀 ▾）
        headers = [w for w in card._list_container.findChildren(st._GroupHeader)]
        self.assertEqual(len(headers), 5)
        labels = {h.text().replace("▾ ", "").replace("▸ ", "") for h in headers}
        self.assertEqual(labels, {"今天", "昨天", "近7天", "近30天", "更早"})
        # 底部信息
        self.assertIn("Demo", card._footer_lb.text())
        self.assertIn("5 个会话", card._footer_lb.text())
    def test_incremental_rebuild_reuses_items(self):
        card, mw = self._make_card()
        card._refresh()
        item_ref = card._items["s-today"]
        # 标题变化后再次刷新 → 复用同一 widget 且文本更新
        mw.history_manager._sessions[0]["title"] = "改名了"
        card._refresh()
        self.assertIs(card._items["s-today"], item_ref)
        self.assertEqual(item_ref._title_lb.text(), "改名了")

    def test_fingerprint_skips_rebuild_when_unchanged(self):
        """指纹门控：列表+主题未变 → 不重建、不 setText"""
        card, mw = self._make_card()
        card._refresh()
        item_ref = card._items["s-today"]
        title_lb = item_ref._title_lb
        # 二次刷新（数据未变）→ 同一 widget 且 QLabel 实例不变（未触发重设）
        card._refresh()
        self.assertIs(card._items["s-today"], item_ref)
        self.assertIs(item_ref._title_lb, title_lb)
        # 当前会话高亮切换（列表结构未变）→ 只更新高亮，不重建
        mw._current_session_id = "s-yest"
        card._refresh()
        self.assertIs(card._items["s-today"], item_ref)
        self.assertTrue(card._items["s-yest"].property("current"))
        self.assertFalse(card._items["s-today"].property("current"))

    def test_wide_narrow_mode_switch(self):
        """响应式：宽模式两行（预览可见），窄模式单行（预览隐藏）"""
        card, mw = self._make_card()
        card.show()  # Qt 对未显示 widget 不派发 resizeEvent，须先 show
        card._refresh()
        card.resize(300, 600)  # 宽模式
        self.assertTrue(card._wide)
        item = card._items["s-today"]
        self.assertTrue(item._preview_lb.isVisible())
        self.assertEqual(item.height(), st._ITEM_H_WIDE)
        card.resize(150, 600)  # 窄模式
        self.assertFalse(card._wide)
        self.assertFalse(item._preview_lb.isVisible())
        self.assertEqual(item.height(), st._ITEM_H_NARROW)
        # 窄模式隐藏头部标题/计数
        self.assertFalse(card._title_lb.isVisible())
        # 超窄：item 宽度 < 130 → 隐藏时间标签，空间全给标题
        self.assertGreater(item.width(), 0)
        if item.width() < 130:
            self.assertFalse(item._time_lb.isVisible())
            item._time_lb.setVisible(True)
            item.resize(150, item.height())
            self.assertTrue(item._time_lb.isVisible())

    def test_elided_label(self):
        """ElideMiddle：长标题不溢出 + tooltip 全文"""
        lb = st._ElidedLabel("超长标题" * 50)
        lb.show()
        lb.resize(80, 20)
        self.assertLessEqual(lb.fontMetrics().horizontalAdvance(lb.text()), 80)
        self.assertEqual(lb.toolTip(), "超长标题" * 50)

    def test_team_mode_no_crash(self):
        """回归：团队会话树线（子控件实现）不再触发 Qt 0xc0000409 崩溃

        原 paintEvent + QPainter.drawLine 在 QSS 环境下崩溃（进程级，无法在
        本进程内捕获）→ 用子进程跑复现脚本，断言退出码 0。
        """
        import subprocess
        import sys

        script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "tests", "repro_team_no_crash.py")
        r = subprocess.run(
            [sys.executable, script],
            capture_output=True,
            timeout=90,
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        )
        self.assertEqual(
            r.returncode, 0,
            f"团队模式子进程崩溃 rc={r.returncode}: {r.stderr.decode(errors='replace')[-400:]}",
        )

    def test_click_switches_session(self):
        card, mw = self._make_card()
        card._refresh()
        card._on_item_clicked("s-yest")
        self.assertEqual(mw._switched, "s-yest")

    def test_new_session(self):
        card, mw = self._make_card()
        card._on_new_clicked()
        self.assertEqual(mw._new_calls, 1)

    def test_archive_session(self):
        card, mw = self._make_card()
        card._refresh()
        card._archive_session(mw, "s-yest")
        sids = {s["session_id"] for s in mw.history_manager._sessions}
        self.assertNotIn("s-yest", sids)
        self.assertEqual(mw._notify_calls, 1)

    def test_archive_current_session_creates_new_first(self):
        card, mw = self._make_card()
        card._refresh()
        card._archive_session(mw, "s-today")
        self.assertEqual(mw._new_calls, 1)  # 先切新会话
        sids = {s["session_id"] for s in mw.history_manager._sessions}
        self.assertNotIn("s-today", sids)

    def test_delete_session(self):
        card, mw = self._make_card()
        card._refresh()
        # 绕过确认弹窗：直接调用删除逻辑会弹 QMessageBox → patch
        import unittest.mock

        with unittest.mock.patch.object(st.QMessageBox, "warning", return_value=st.QMessageBox.Yes):
            card._delete_session(mw, "s-3d")
        sids = {s["session_id"] for s in mw.history_manager._sessions}
        self.assertNotIn("s-3d", sids)
        self.assertEqual(mw._notify_calls, 1)

    def test_rename_session(self):
        card, mw = self._make_card()
        card._refresh()
        import unittest.mock

        with unittest.mock.patch.object(st.QInputDialog, "getText", return_value=("新标题A", True)):
            card._rename_session(mw, "s-yest")
        self.assertEqual(mw.history_manager._sessions[1]["title"], "新标题A")
        self.assertEqual(mw._notify_calls, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
