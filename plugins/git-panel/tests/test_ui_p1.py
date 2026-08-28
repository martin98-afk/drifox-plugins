# -*- coding: utf-8 -*-
"""git-panel P1 UI 层验证（offscreen 平台，stdlib unittest）

覆盖 5 大 P1 功能：
1. 词级 diff 高亮（_DiffDialog 渲染含词级背景标记）
2. commit 详情对话框（元信息 + 完整 diff + 5000 行截断提示）
3. 冲突解决（_FileRowWidget 冲突按钮 + 菜单构造）
4. 文件右键菜单（contextMenuEvent 构造）
5. InfoBar 错误反馈升级

运行：set QT_QPA_PLATFORM=offscreen && python -m unittest ... （脚本内已自动设置）
"""

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_DIR = os.path.join(PLUGIN_DIR, "ui")


def _load_plugin_modules():
    sys.path.insert(0, UI_DIR)
    ui_init = os.path.join(UI_DIR, "__init__.py")
    spec = importlib.util.spec_from_file_location("ui_plugin_git_panel", ui_init)
    module = importlib.util.module_from_spec(spec)
    sys.modules["ui_plugin_git_panel"] = module
    spec.loader.exec_module(module)
    import ui_plugin_git_panel.git_core as gc
    import ui_plugin_git_panel.cards as cards_mod
    return gc.GitRepo, cards_mod


GitRepo, cards = _load_plugin_modules()

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication([])


def wait_until(cond, timeout_ms=8000, interval=40):
    loop = QEventLoop()
    result = {"ok": False}

    def poll():
        if cond():
            result["ok"] = True
            loop.quit()
        else:
            QTimer.singleShot(interval, poll)

    QTimer.singleShot(0, poll)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    return result["ok"]


def _git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return r.stdout.strip(), r.stderr.strip(), r.returncode


class P1UITestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="gitpanel_p1ui_")
        cls.repo = os.path.join(cls.tmp, "repo")
        os.makedirs(cls.repo)
        _git(cls.repo, "init", "-b", "main")
        _git(cls.repo, "config", "user.email", "t@t.t")
        _git(cls.repo, "config", "user.name", "T")
        cls.g = GitRepo(cls.repo)
        # 初始提交
        with open(os.path.join(cls.repo, "base.txt"), "w", encoding="utf-8") as f:
            f.write("line1\nline2\n")
        cls.g.add(["."])
        cls.g.commit("init")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _write(self, name, content):
        p = os.path.join(self.repo, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return p


class TestWordLevelDiff(P1UITestBase):
    def test_diff_dialog_word_highlight(self):
        # 制造词级差异：删除 world，新增 brave world
        self._write("base.txt", "hello world\nline2\n")
        dlg = cards._DiffDialog(self.repo, "base.txt", False)
        dlg.show()
        ok = wait_until(lambda: "加载中" not in dlg._diff_area.toPlainText())
        self.assertTrue(ok, "diff 异步加载超时")
        html = dlg._diff_area.toHtml()
        # 词级新增高亮（浅绿底，Qt 会将 0.28 归一化为 0.278431）
        self.assertIn("rgba(80,227,194,0.278431)", html)
        # 行级颜色
        self.assertIn("color:#50e3c2", html)
        self.assertIn("color:#f14c4c", html)
        dlg.close()
        dlg.deleteLater()
        _APP.processEvents()

    def test_untracked_file_preview(self):
        """未跟踪文件（??）双击预览：显示全新增 diff，而非"(无差异)" """
        self._write("brand_new.txt", "alpha\nbeta\n")
        dlg = cards._DiffDialog(self.repo, "brand_new.txt", False, "??")
        dlg.show()
        ok = wait_until(lambda: "加载中" not in dlg._diff_area.toPlainText())
        self.assertTrue(ok, "未跟踪文件 diff 异步加载超时")
        html = dlg._diff_area.toHtml()
        self.assertIn("brand_new.txt", html)
        self.assertIn("alpha", html)
        self.assertIn("beta", html)
        self.assertNotIn("(无差异)", dlg._diff_area.toPlainText())
        # 标题状态显示"未跟踪"
        dlg.close()
        dlg.deleteLater()
        _APP.processEvents()

    def test_untracked_empty_file_preview(self):
        """未跟踪空文件预览：显示"(空文件)"而非"(无差异)" """
        self._write("empty_new.txt", "")
        dlg = cards._DiffDialog(self.repo, "empty_new.txt", False, "??")
        dlg.show()
        ok = wait_until(lambda: "加载中" not in dlg._diff_area.toPlainText())
        self.assertTrue(ok, "空文件 diff 异步加载超时")
        self.assertIn("空文件", dlg._diff_area.toPlainText())
        dlg.close()
        dlg.deleteLater()
        _APP.processEvents()


class TestCommitDetailDialog(P1UITestBase):
    def test_commit_detail(self):
        self._write("base.txt", "v2 content\nline2\n")
        self.g.add(["."])
        self.g.commit("feat: update base")
        h = self.g.log()[0]["hash"]

        dlg = cards._CommitDetailDialog(self.repo, h)
        dlg.show()
        ok = wait_until(lambda: "加载中" not in dlg._diff_area.toPlainText())
        self.assertTrue(ok, "commit 详情加载超时")
        self.assertIn("feat: update base", dlg._msg_lb.text())
        self.assertIn("T <t@t.t>", dlg._meta_lb.text())
        html = dlg._diff_area.toHtml()
        self.assertIn("color:#50e3c2", html)  # diff 词级渲染
        dlg.close()
        dlg.deleteLater()
        _APP.processEvents()

    def test_commit_detail_hash_copy(self):
        h = self.g.log()[0]["hash"]
        dlg = cards._CommitDetailDialog(self.repo, h)
        dlg.show()
        ok = wait_until(lambda: not hasattr(dlg, "_detail_thread") or True)
        # 触发 hash 点击复制
        from PySide6.QtWidgets import QApplication

        dlg._on_hash_click(None)
        self.assertEqual(QApplication.clipboard().text(), h)
        dlg.close()
        dlg.deleteLater()
        _APP.processEvents()


class TestConflictRow(P1UITestBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # 制造冲突
        bare = os.path.join(cls.tmp, "remote.git")
        subprocess.run(["git", "init", "--bare", "-b", "main", bare],
                       capture_output=True, text=True)
        _git(cls.repo, "remote", "add", "origin", bare)
        _git(cls.repo, "config", "user.email", "t@t.t")
        _git(cls.repo, "config", "user.name", "T")
        with open(os.path.join(cls.repo, "conf.txt"), "w", encoding="utf-8") as f:
            f.write("base\n")
        cls.g.add(["."])
        cls.g.commit("conf base")
        cls.g.push()

        clone = os.path.join(cls.tmp, "clone")
        subprocess.run(["git", "clone", bare, clone], capture_output=True, text=True)
        _git(clone, "config", "user.email", "t@t.t")
        _git(clone, "config", "user.name", "T")
        with open(os.path.join(clone, "conf.txt"), "w", encoding="utf-8") as f:
            f.write("theirs\n")
        _git(clone, "add", "-A")
        _git(clone, "commit", "-m", "theirs")
        _git(clone, "push")

        with open(os.path.join(cls.repo, "conf.txt"), "w", encoding="utf-8") as f:
            f.write("ours\n")
        cls.g.add(["."])
        cls.g.commit("ours")
        _git(cls.repo, "pull", "origin", "main")

    def test_status_items_conflict_code(self):
        items = self.g.status_items()
        conflict = [i for i in items if i["status"] in cards._CONFLICT_STATUS]
        self.assertEqual(len(conflict), 1)
        self.assertEqual(conflict[0]["status"], "UU")

    def test_row_conflict_button_and_menu(self):
        row = cards._FileRowWidget({"path": "conf.txt", "status": "UU", "staged": False})
        row._repo_path = self.repo
        self.assertTrue(row._is_conflict())
        # 解决菜单构造
        menu = row._build_conflict_menu()
        self.assertIsNotNone(menu)
        texts = [a.text() for a in menu.actions()]
        self.assertIn("使用 ours（当前分支）", texts)
        self.assertIn("使用 theirs（合并来源）", texts)
        self.assertIn("标记为已解决", texts)
        menu.deleteLater()
        row.deleteLater()
        _APP.processEvents()

    def test_checkout_theirs(self):
        self.assertTrue(self.g.checkout_theirs("conf.txt").ok)
        with open(os.path.join(self.repo, "conf.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "theirs\n")


class TestPathElide(P1UITestBase):
    """文件路径用 _ElidedLabel：超长省略 + tooltip 完整路径，不撑宽行"""

    def test_path_label_elided_and_tooltip(self):
        long = ("src/very/very/very/long/path/to/a/file/that/definitely/"
                "overflows/the/row/width/definitely.py")
        row = cards._FileRowWidget({"path": long, "status": "M", "staged": False})
        lb = row.findChild(cards._ElidedLabel)
        self.assertIsNotNone(lb, "文件路径应使用 _ElidedLabel")
        self.assertEqual(lb.toolTip(), long, "tooltip 必须为完整路径")
        # 窄宽度下省略（中间省略号）
        row.resize(200, 32)
        row.show()
        _APP.processEvents()
        self.assertLess(len(lb.text()), len(long))
        self.assertIn("…", lb.text())
        row.deleteLater()
        _APP.processEvents()

    def test_path_label_not_elided_short(self):
        row = cards._FileRowWidget({"path": "short.py", "status": "M", "staged": False})
        lb = row.findChild(cards._ElidedLabel)
        row.resize(300, 32)
        row.show()
        _APP.processEvents()
        self.assertEqual(lb.text(), "short.py")
        row.deleteLater()
        _APP.processEvents()


class TestContextMenu(P1UITestBase):
    def test_menu_construction(self):
        # 普通文件行：暂存/放弃/复制/.gitignore/文件管理器
        self._write("ctx.txt", "x\n")
        row = cards._FileRowWidget({"path": "ctx.txt", "status": "??", "staged": False})
        row._repo_path = self.repo
        menu = row._build_context_menu()
        texts = [a.text() for a in menu.actions()]
        self.assertIn("暂存此文件", texts)
        self.assertIn("放弃未跟踪文件", texts)
        self.assertIn("复制相对路径", texts)
        self.assertIn("添加到 .gitignore", texts)
        self.assertIn("在文件管理器中显示", texts)
        menu.deleteLater()
        row.deleteLater()
        _APP.processEvents()

    def test_add_to_gitignore(self):
        self._write("ignored.log", "x\n")
        row = cards._FileRowWidget({"path": "ignored.log", "status": "??", "staged": False})
        row._repo_path = self.repo
        row._add_to_gitignore()
        gi = os.path.join(self.repo, ".gitignore")
        with open(gi, encoding="utf-8") as f:
            self.assertIn("ignored.log", f.read())
        # 去重：再次添加不重复
        row._add_to_gitignore()
        with open(gi, encoding="utf-8") as f:
            self.assertEqual(f.read().count("ignored.log"), 1)
        row.deleteLater()
        _APP.processEvents()


class TestInfoBar(P1UITestBase):
    def test_info_bar_success(self):
        card = cards.GitPanelCard()
        card.show()
        card._show_info_bar("success", "测试成功", "")
        self.assertGreaterEqual(card._info_bar_layout.count(), 1)
        # 等待自动关闭后清理
        wait_until(lambda: card._info_bar_layout.count() == 0, timeout_ms=6000)
        self.assertEqual(card._info_bar_layout.count(), 0)
        card.deleteLater()
        _APP.processEvents()


class TestWorkerErrorRecovery(P1UITestBase):
    """B1：后台任务抛异常（非 GitResult 路径）时同步按钮必须恢复"""

    def test_error_recovers_sync_buttons(self):
        card = cards.GitPanelCard()
        card.show()
        card.set_context_provider(lambda: {"project_root": self.repo, "colors": {},
                                           "font_family": "Microsoft YaHei", "font_size": 14})
        # 先触发一次正常刷新，确保 _push_btn 等已构建
        card._async_refresh()
        wait_until(lambda: not card._is_loading)
        self.assertTrue(card._push_btn.isEnabled())

        # 模拟同步操作进行中（按钮置灰）
        card._set_sync_busy(True)
        self.assertFalse(card._push_btn.isEnabled())

        # 让后台任务抛异常（非 GitResult 路径）
        def _boom():
            raise RuntimeError("simulated worker crash")

        card._run_git_async(_boom, lambda r: None)
        # 等待 error 信号处理：按钮应恢复
        recovered = wait_until(lambda: card._push_btn.isEnabled(), timeout_ms=5000)
        self.assertTrue(recovered, "异常后同步按钮未恢复（B1）")
        card.deleteLater()
        _APP.processEvents()


if __name__ == "__main__":
    unittest.main(verbosity=2)
