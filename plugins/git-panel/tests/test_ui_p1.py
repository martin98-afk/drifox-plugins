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
    import ui_plugin_git_panel.diff_renderer as diff_renderer_mod
    import ui_plugin_git_panel.cards as cards_mod
    return gc.GitRepo, diff_renderer_mod, cards_mod


GitRepo, diff_renderer, cards = _load_plugin_modules()

from PyQt5.QtCore import QEventLoop, QTimer  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402
from qfluentwidgets import isDarkTheme  # noqa: E402

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
    loop.exec_()
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

    def tearDown(self):
        """排空延迟删除队列，避免残留控件跨用例污染。

        deleteLater() 只是投递 DeferredDelete 事件，裸 processEvents() 不保证
        在本次调用中处理完；残留的顶层窗口会被下一个用例的
        cards._dialog_parent() 回退分支选中作为对话框父窗口，父窗口销毁时
        连带销毁对话框 → 下个用例拿到已删除的 C++ 对象（Abort）。
        这里用 sendPostedEvents 强制在用例边界清空。
        """
        from PyQt5.QtCore import QCoreApplication, QEvent

        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        _APP.processEvents()

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
        # 词级新增高亮：断言随实际主题选中的调色板颜色，而非写死深色值
        # （offscreen 环境为浅色主题，写死深色色值会误报失败）
        pal = diff_renderer._palette(isDarkTheme())
        self.assertIn(pal["add"], html)
        self.assertIn(pal["del"], html)
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
        # diff 词级渲染：按实际主题调色板断言（浅色/深色环境均成立）
        pal = diff_renderer._palette(isDarkTheme())
        self.assertIn(pal["add"], html)
        dlg.close()
        dlg.deleteLater()
        _APP.processEvents()

    def test_commit_detail_hash_copy(self):
        h = self.g.log()[0]["hash"]
        dlg = cards._CommitDetailDialog(self.repo, h)
        dlg.show()
        ok = wait_until(lambda: not hasattr(dlg, "_detail_thread") or True)
        # 触发 hash 点击复制
        from PyQt5.QtWidgets import QApplication

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
        # --no-rebase：显式 merge 策略（裸 pull 在 git 2.27+ 无配置机器上
        # 会直接报错不进入合并，测试须与机器配置无关）
        _git(cls.repo, "pull", "--no-rebase", "origin", "main")

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


class TestTabFont(P1UITestBase):
    """tab 名的字体族必须取系统 UI 字体，不跟随宿主主题字体（行楷等）；字号比正文字号小 3 号"""

    def test_tab_font_not_theme_family(self):
        card = cards.GitPanelCard()
        card.set_context_provider(lambda: {"project_root": self.repo, "colors": {},
                                           "font_family": "Xingkai SC", "font_size": 16})
        card._apply_latest_theme()
        # 根控件仍是宿主主题字体，tab 名单独回落系统字体
        self.assertEqual(card.font().family(), "Xingkai SC")
        self.assertEqual(card._tabs.font().family(), QApplication.font().family())
        self.assertEqual(card._tabs.font().pointSize(), 13)
        card.deleteLater()
        _APP.processEvents()


class TestChangesTooltip(P1UITestBase):
    """文件行 tooltip 走插件自绘气泡：原生 QToolTip 字号被宿主放大且底色不受控"""

    def test_viewport_tooltip_uses_bubble(self):
        from PyQt5.QtCore import QEvent, QPoint
        from PyQt5.QtGui import QHelpEvent

        view = cards.ChangesView()
        view.resize(420, 240)
        view.set_tooltip_theme("#ffffff", "#303032", "#3d3d3d", "Microsoft YaHei", 15)
        view.set_items([
            {"path": "plugins/git-panel/ui/cards.py", "status": "M", "staged": False},
        ])
        view.show()
        index = view.file_indexes()[0]
        pos = view.visualRect(index).center()
        ev = QHelpEvent(QEvent.ToolTip, pos, view.viewport().mapToGlobal(pos))
        # 拦下原生 tooltip，改由自绘气泡显示
        self.assertTrue(view.viewportEvent(ev))
        self.assertEqual(view._tip.text(),
                         "plugins/git-panel/ui/cards.py\n工作区 · M")
        self.assertEqual(view._tip.font().pixelSize(), 15)
        view._tip.hide()
        view.deleteLater()
        _APP.processEvents()


class TestInfoBar(P1UITestBase):
    def test_info_bar_success(self):
        card = cards.GitPanelCard()
        card.show()
        card._show_info_bar("success", "测试成功", "")
        self.assertGreaterEqual(card._info_bar_layout.count(), 1)
        # 等待自动关闭后清理（success 的 duration=6s，等待窗口须留余量：
        # 恰好 6000ms 时自动关闭计时器与轮询超时同刻竞争，必然取到 count()!=0）
        wait_until(lambda: card._info_bar_layout.count() == 0, timeout_ms=12000)
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


class TestCommitPromptAssembly(P1UITestBase):
    """AI 生成提交描述的 prompt 拼装：按文件截断、清单、风格样例、总预算"""

    def _stage_changes(self):
        self._write("base.txt", "line1\nline2-mod\nline3\n")
        self._write("small.txt", "x\n")
        big = "\n".join(f"line {i}" for i in range(1500))
        self._write("big.py", big + "\n")
        self.g.add(["."])

    def test_file_list_and_context_present(self):
        self._stage_changes()
        card = cards.GitPanelCard()
        card._repo_path = self.repo
        files = self.g.staged_file_diffs(2000)
        prompt = card._build_commit_user_prompt(self.g, files)
        self.assertIn("# 仓库详情", prompt)
        self.assertIn(f"仓库名：{os.path.basename(self.repo)}", prompt)
        self.assertIn("# 变更文件", prompt)
        self.assertIn("big.py", prompt)
        self.assertIn("# 最近提交", prompt)
        card.deleteLater()
        _APP.processEvents()

    def test_per_file_truncation_marked(self):
        self._stage_changes()
        files = self.g.staged_file_diffs(800)
        big = next(f for f in files if f["path"] == "big.py")
        self.assertTrue(big["truncated"], "超过单文件上限应标记 truncated")
        self.assertLessEqual(len(big["diff"]), 800 + 120, "截断后不应显著超出限额")
        self.assertIn("此文件 diff 已截断", big["diff"])
        small = next(f for f in files if f["path"] == "small.txt")
        self.assertFalse(small["truncated"])

    def test_files_sorted_by_change_volume(self):
        self._stage_changes()
        files = self.g.staged_file_diffs(20000)
        volumes = [f["add"] + f["del"] for f in files]
        self.assertEqual(volumes, sorted(volumes, reverse=True), "应按改动量降序")

    def test_total_budget_drops_oversized_file_without_starving_small_ones(self):
        """超大文件装不进总预算时应降级为清单条目，小文件 diff 保留"""
        self._stage_changes()
        card = cards.GitPanelCard()
        card._repo_path = self.repo
        orig = cards._AI_TOTAL_DIFF_BUDGET
        try:
            cards._AI_TOTAL_DIFF_BUDGET = 400
            files = self.g.staged_file_diffs(20000)
            prompt = card._build_commit_user_prompt(self.g, files)
            self.assertIn("diff 未包含", prompt)
            self.assertIn("small.txt", prompt)
            # 小文件 diff 仍应出现，超大文件不被强制塞入
            self.assertNotIn("## big.py", prompt)
        finally:
            cards._AI_TOTAL_DIFF_BUDGET = orig
            card.deleteLater()
            _APP.processEvents()

    def test_returns_single_code_section_when_nothing_fits(self):
        """预算极小时兜底：至少给一个文件的截断 diff"""
        self._stage_changes()
        card = cards.GitPanelCard()
        card._repo_path = self.repo
        orig = cards._AI_TOTAL_DIFF_BUDGET
        try:
            cards._AI_TOTAL_DIFF_BUDGET = 100
            files = self.g.staged_file_diffs(20000)
            prompt = card._build_commit_user_prompt(self.g, files)
            self.assertIn("# 代码改动", prompt)
            self.assertIn("因总预算截断", prompt)
        finally:
            cards._AI_TOTAL_DIFF_BUDGET = orig
            card.deleteLater()
            _APP.processEvents()


class TestTreeDirStaging(P1UITestBase):
    """文件树模式：目录节点聚合子文件，支持整目录暂存/取消暂存"""

    def setUp(self):
        # set_mode 会把模式持久化到 QSettings，污染其他用例（如切换按钮文案断言）
        from PyQt5.QtCore import QSettings
        self._settings = QSettings("DriFox", "git-panel")
        self._saved_mode = self._settings.value("changes_view", "list")

    def tearDown(self):
        self._settings.setValue("changes_view", self._saved_mode)
        super().tearDown()

    def _make_tree(self):
        import ui_plugin_git_panel.changes_view as cv
        self.cv = cv
        view = cv.ChangesView()
        view.set_mode("tree")
        view.set_items([
            {"path": "alpha/a.txt", "status": "??", "staged": False},
            {"path": "alpha/beta/b.txt", "status": "??", "staged": False},
            {"path": "gamma/g.txt", "status": "??", "staged": False},
        ])
        return view

    def test_dir_node_aggregates_nested_files(self):
        view = self._make_tree()
        dirs = {i.data(self.cv.DIR_ROLE)["path"]: i.data(self.cv.DIR_ROLE)
                for i in view._all_indexes() if i.data(self.cv.DIR_ROLE)}
        self.assertIn("alpha", dirs)
        self.assertIn("alpha/beta", dirs)
        # 父目录必须包含嵌套子目录下的文件
        self.assertEqual(sorted(dirs["alpha"]["files"]),
                         ["alpha/a.txt", "alpha/beta/b.txt"])
        view.deleteLater()
        _APP.processEvents()

    def test_dir_action_is_stage_when_children_unstaged(self):
        view = self._make_tree()
        idx = next(i for i in view._all_indexes()
                   if (i.data(self.cv.DIR_ROLE) or {}).get("path") == "alpha")
        info = idx.data(self.cv.DIR_ROLE)
        self.assertEqual(view._action_for(info), "stage")
        view.deleteLater()
        _APP.processEvents()

    def test_dir_action_is_unstage_when_all_children_staged(self):
        import ui_plugin_git_panel.changes_view as cv
        view = cv.ChangesView()
        view.set_mode("tree")
        view.set_items([
            {"path": "alpha/a.txt", "status": "M", "staged": True},
            {"path": "alpha/b.txt", "status": "M", "staged": True},
        ])
        idx = next(i for i in view._all_indexes()
                   if (i.data(cv.DIR_ROLE) or {}).get("path") == "alpha")
        self.assertEqual(view._action_for(idx.data(cv.DIR_ROLE)), "unstage")
        view.deleteLater()
        _APP.processEvents()

    def test_batch_stage_and_unstage_via_repo(self):
        """目录批量路径真实落到 git add / restore --staged"""
        os.makedirs(os.path.join(self.repo, "alpha", "beta"), exist_ok=True)
        self._write("alpha/a.txt", "a\n")
        self._write("alpha/beta/b.txt", "b\n")
        paths = ["alpha/a.txt", "alpha/beta/b.txt"]
        self.assertTrue(self.g.add(paths).ok)
        staged = {i["path"] for i in self.g.status_items() if i["staged"]}
        self.assertTrue(set(paths).issubset(staged), "批量暂存未生效")
        self.assertTrue(self.g.restore_staged(paths).ok)
        staged_after = {i["path"] for i in self.g.status_items() if i["staged"]}
        self.assertFalse(set(paths) & staged_after, "批量取消暂存未生效")

    def test_restore_staged_falls_back_on_empty_repo(self):
        """空仓库（无 HEAD）取消暂存回退 rm --cached"""
        import tempfile
        tmp = tempfile.mkdtemp(prefix="gp_empty_repo_")
        try:
            _git(tmp, "init", "-b", "main")
            _git(tmp, "config", "user.email", "t@t.t")
            _git(tmp, "config", "user.name", "T")
            with open(os.path.join(tmp, "x.txt"), "w", encoding="utf-8") as f:
                f.write("x\n")
            repo = GitRepo(tmp)
            self.assertTrue(repo.add(["x.txt"]).ok)
            res = repo.restore_staged(["x.txt"])
            self.assertTrue(res.ok, f"空仓库取消失败: {res.stderr}")
            statuses = {i["path"]: i["status"] for i in repo.status_items()}
            self.assertEqual(statuses.get("x.txt"), "??")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
