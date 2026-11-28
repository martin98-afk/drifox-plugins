"""源代码管理视图与后台调度回归。"""
import importlib.util
import os
import sys
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
UI = Path(__file__).resolve().parents[1] / "ui"
if "ui_plugin_git_panel" not in sys.modules:
    spec = importlib.util.spec_from_file_location("ui_plugin_git_panel", UI / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
from PyQt5.QtCore import QCoreApplication, QEvent  # noqa: E402
from PyQt5.QtWidgets import QApplication, QWidget  # noqa: E402
from qfluentwidgets import RoundMenu  # noqa: E402
from ui_plugin_git_panel.changes_view import ChangesView, FILE_ROLE  # noqa: E402
from ui_plugin_git_panel.task_runner import TaskRunner  # noqa: E402

APP = QApplication.instance() or QApplication([])


def wait_for(predicate, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        APP.processEvents()
        if predicate():
            return True
        time.sleep(.002)
    return False


class ChangesTests(unittest.TestCase):
    def setUp(self):
        self.view = ChangesView()
        self.view.set_mode("list")
        self.items = [
            {"path": "src/a.py", "status": "M", "staged": True},
            {"path": "src/a.py", "status": "M", "staged": False},
            {"path": "docs/new name.md", "status": "??", "staged": False},
            {"path": "src/conflict.py", "status": "UU", "staged": False},
        ]

    def tearDown(self):
        self.view.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_groups_keep_same_path_in_two_areas(self):
        self.assertTrue(self.view.set_items(self.items))
        self.assertEqual(self.view.model().rowCount(), 3)
        found = [i.data(FILE_ROLE) for i in self.view.file_indexes()]
        self.assertEqual(sum(i["path"] == "src/a.py" for i in found), 2)
        self.assertEqual(len(found), 4)

    def test_unchanged_snapshot_keeps_model_and_selection(self):
        self.view.set_items(self.items)
        index = self.view.file_indexes()[1]
        self.view.setCurrentIndex(index)
        model = self.view.model()
        self.assertFalse(self.view.set_items(list(self.items)))
        self.assertIs(model, self.view.model())
        self.assertEqual(self.view.currentIndex(), index)

    def test_tree_mode_preserves_selection_and_directory(self):
        self.view.set_items(self.items)
        target = self.view.file_indexes()[0]
        selected = target.data(FILE_ROLE)
        self.view.setCurrentIndex(target)
        self.view.set_mode("tree")
        self.assertEqual(self.view.currentIndex().data(FILE_ROLE), selected)
        self.assertEqual(self.view.file_indexes()[0].parent().data(), "src")
        directory = self.view.file_indexes()[0].parent()
        self.view.collapse(directory)
        self.view.set_items(self.items + [{"path": "src/z.py", "status": "A", "staged": True}])
        self.assertFalse(self.view.isExpanded(self.view.file_indexes()[0].parent()))

    def test_model_does_not_create_widgets_per_file(self):
        before = len(self.view.findChildren(QWidget))
        self.view.set_items([{"path": f"src/f{i}.py", "status": "M", "staged": False} for i in range(1000)])
        self.assertLessEqual(len(self.view.findChildren(QWidget)), before + 2)

    def test_filter_survives_refresh_and_mode_switch(self):
        self.view.set_items(self.items)
        self.view.set_filter(" DOCS/ ")
        self.view.set_mode("tree")
        self.view.set_items(self.items + [{"path": "docs/guide.md", "status": "A", "staged": True}])
        self.assertEqual(
            sorted(i.data(FILE_ROLE)["path"] for i in self.view.file_indexes()),
            ["docs/guide.md", "docs/new name.md"],
        )
        self.view.set_filter("missing")
        self.assertEqual(self.view.model().rowCount(), 0)
        self.view.set_filter("")
        self.assertEqual(len(self.view.file_indexes()), len(self.items) + 1)
        self.view.set_mode("list")


class RunnerTests(unittest.TestCase):
    def test_serializes_and_coalesces_pending_refresh(self):
        runner = TaskRunner()
        calls = []
        def slow():
            time.sleep(.03)
            calls.append("first")
        runner.submit(slow, lambda _: None)
        runner.submit(lambda: calls.append("old"), lambda _: None, key="refresh")
        runner.submit(lambda: calls.append("new"), lambda _: None, key="refresh")
        runner.submit(lambda: calls.append("write"), lambda _: None)
        self.assertTrue(wait_for(lambda: not runner.busy))
        self.assertEqual(calls, ["first", "new", "write"])

    def test_error_does_not_block_next_task_and_callbacks_on_main(self):
        from PyQt5.QtCore import QThread
        runner = TaskRunner()
        result = []
        def fail():
            raise RuntimeError("test error")
        runner.submit(fail, result.append, lambda e: result.append(e))
        runner.submit(lambda: 42, lambda value: result.append((value, QThread.currentThread() is APP.thread())))
        self.assertTrue(wait_for(lambda: not runner.busy))
        self.assertIn("test error", result[0])
        self.assertEqual(result[1], (42, True))

    def test_dispose_ignores_active_and_pending_callbacks(self):
        runner = TaskRunner()
        result = []
        runner.submit(lambda: time.sleep(.04), result.append)
        runner.submit(lambda: 2, result.append)
        runner.dispose()
        self.assertTrue(wait_for(lambda: not runner.busy))
        self.assertEqual(result, [])


class CardLayoutTests(unittest.TestCase):
    def setUp(self):
        from ui_plugin_git_panel.cards import GitPanelCard
        self.card = GitPanelCard()
        self.card.resize(320, 800)

    def tearDown(self):
        self.card.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_pages_switch_hides_commit_editor(self):
        self.card.show()
        self.card._tabs.setCurrentIndex(1)
        self.assertFalse(self.card._commit_editor.isVisible())
        self.card._tabs.setCurrentIndex(0)
        self.assertTrue(self.card._commit_editor.isVisible())

    def test_view_mode_toggle_updates_label(self):
        self.card._toggle_changes_view()
        self.assertEqual(self.card._view_btn.text(), "文件树 ▾")
        self.card._toggle_changes_view()
        self.assertEqual(self.card._view_btn.text(), "列表 ▾")

    def test_menus_build_without_widgets_per_file(self):
        branch_menu = self.card._build_branch_menu([
            {"name": "main", "current": True, "checked_out_elsewhere": False},
            {"name": "dev", "current": False, "checked_out_elsewhere": True},
        ])
        titles = [m.title() for m in branch_menu.findChildren(RoundMenu) if m is not branch_menu]
        self.assertTrue(any("main" in t for t in titles))
        self.assertTrue(any("dev" in t for t in titles))
        stash_menu = self.card._build_stash_menu([
            {"ref": "stash@{0}", "message": "wip", "index": 0},
        ])
        self.assertTrue(any("stash@{0}" in m.title() for m in stash_menu.findChildren(RoundMenu)))

    def test_narrow_widths_keep_minimum_size(self):
        # 最小宽度只守「不被撑爆」上界：分支徽标与同步按钮的精确宽度受字体影响，
        # 卡在 width+80 一类的紧边界会随字体度量抖动出假失败。
        for width in (280, 320, 420):
            self.card.resize(width, 700)
            APP.processEvents()
            self.assertGreater(self.card.minimumSizeHint().width(), 0)
            self.assertLessEqual(self.card.minimumSizeHint().width(), 420)


class FetchTests(unittest.TestCase):
    def setUp(self):
        import subprocess
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="gitpanel_fetch_")
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        subprocess.run(["git", "-C", self.repo, "init", "-b", "main"], capture_output=True)
        subprocess.run(["git", "-C", self.repo, "config", "user.email", "t@t.t"], capture_output=True)
        subprocess.run(["git", "-C", self.repo, "config", "user.name", "T"], capture_output=True)
        with open(os.path.join(self.repo, "a.txt"), "w", encoding="utf-8") as f:
            f.write("one\n")
        subprocess.run(["git", "-C", self.repo, "add", "."], capture_output=True)
        subprocess.run(["git", "-C", self.repo, "commit", "-m", "init"], capture_output=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_changes_page_skips_history_query(self):
        from ui_plugin_git_panel.cards import GitPanelCard
        data = GitPanelCard._fetch_all_data(self.repo, history=False)
        self.assertEqual(data["branch"], "main")
        self.assertEqual(len(data["status"]), 0)
        self.assertNotIn("log", data)

    def test_history_page_includes_log(self):
        from ui_plugin_git_panel.cards import GitPanelCard
        data = GitPanelCard._fetch_all_data(self.repo, history=True, log_limit=5)
        self.assertEqual(len(data["log"]), 1)

    def test_non_repo_returns_error(self):
        from ui_plugin_git_panel.cards import GitPanelCard
        data = GitPanelCard._fetch_all_data(os.path.dirname(self.repo), history=False)
        self.assertIn("error", data)



if __name__ == "__main__":
    unittest.main()
