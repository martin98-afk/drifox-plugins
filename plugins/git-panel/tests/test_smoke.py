# -*- coding: utf-8 -*-
"""git-panel P1 冒烟测试（stdlib unittest，无第三方测试依赖）

覆盖：
- GitRepo 在临时仓库的端到端操作（status/add/restore_staged/commit/分支/冲突检测）
- diff_renderer 词级高亮输出断言
- _CommitDetailDialog._parse_show_output 解析断言

运行：python -m unittest plugins.git_panel.tests.test_smoke -v
（或 cd plugins/git-panel && python -m unittest tests.test_smoke -v）
"""

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

# ── 模拟 DriFox 运行时加载插件 UI 模块（目录名含连字符，不能直接 import） ──

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
    import ui_plugin_git_panel.diff_renderer as dr
    import ui_plugin_git_panel.cards as cards_mod
    return gc.GitRepo, dr, cards_mod


GitRepo, diff_renderer, cards = _load_plugin_modules()

def _git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return r.stdout.strip(), r.stderr.strip(), r.returncode


class TempRepoMixin:
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="gitpanel_p1_")
        self.repo = os.path.join(self._tmp, "repo")
        os.makedirs(self.repo)
        _git(self.repo, "init", "-b", "main")
        _git(self.repo, "config", "user.email", "t@t.t")
        _git(self.repo, "config", "user.name", "Tester")
        self.g = GitRepo(self.repo)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write(self, name, content):
        p = os.path.join(self.repo, name)
        os.makedirs(os.path.dirname(p), exist_ok=True) if os.path.dirname(name) else None
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return p


class TestGitRepoEndToEnd(TempRepoMixin, unittest.TestCase):
    def test_status_and_stage_cycle(self):
        self._write("a.txt", "v1\n")
        self.g.add(["."])
        self.g.commit("init")
        # 修改 + 新增
        self._write("a.txt", "v2\n")
        self._write("b.txt", "new\n")
        st = dict(self.g.status())
        self.assertEqual(st.get("a.txt"), " M")
        self.assertEqual(st.get("b.txt"), "??")
        # 暂存
        self.assertTrue(self.g.add(["a.txt"]).ok)
        st = dict(self.g.status())
        self.assertEqual(st.get("a.txt"), "M ")
        # 取消暂存
        self.assertTrue(self.g.restore_staged(["a.txt"]).ok)
        st = dict(self.g.status())
        self.assertEqual(st.get("a.txt"), " M")
        # 放弃
        self.assertTrue(self.g.checkout_discard(["a.txt"]).ok)
        with open(os.path.join(self.repo, "a.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "v1\n")

    def test_commit_and_branch(self):
        self._write("a.txt", "x\n")
        self.g.add(["."])
        self.assertTrue(self.g.commit("first").ok)
        self.assertGreaterEqual(len(self.g.log()), 1)
        # amend
        self.assertTrue(self.g.commit("first amended", amend=True).ok)
        # 分支
        self.assertTrue(self.g.branch_create("dev").ok)
        self.assertEqual(self.g.branch(), "dev")
        self.assertTrue(self.g.branch_checkout("main").ok)
        self.assertTrue(self.g.branch_delete("dev").ok)
        names = [b["name"] for b in self.g.branch_list()]
        self.assertNotIn("dev", names)

    def test_show_commit(self):
        self._write("a.txt", "x\n")
        self.g.add(["."])
        self.g.commit("hello commit")
        h = self.g.log()[0]["hash"]
        res = self.g.show_commit(h)
        self.assertTrue(res.ok)
        self.assertIn("hello commit", res.stdout)
        self.assertIn("diff --git", res.stdout)

    def test_conflict_detection(self):
        """制造合并冲突，验证 status_items 识别 UU 冲突码"""
        # 通过 bare 远程协作：repo A 与 clone 双方改同一文件后合并
        _git(self.repo, "config", "user.email", "t@t.t")
        _git(self.repo, "config", "user.name", "T")
        self._write("conf.txt", "base\n")
        self.g.add(["."])
        self.g.commit("base")

        bare = os.path.join(self._tmp, "remote.git")
        subprocess.run(["git", "init", "--bare", "-b", "main", bare],
                       capture_output=True, text=True)
        _git(self.repo, "remote", "add", "origin", bare)
        self.assertTrue(self.g.push().ok)

        clone = os.path.join(self._tmp, "clone")
        subprocess.run(["git", "clone", bare, clone], capture_output=True, text=True)
        _git(clone, "config", "user.email", "t@t.t")
        _git(clone, "config", "user.name", "T")
        # 双方各改 conf.txt
        with open(os.path.join(clone, "conf.txt"), "w", encoding="utf-8") as f:
            f.write("theirs\n")
        _git(clone, "add", "-A")
        _git(clone, "commit", "-m", "theirs change")
        _git(clone, "push")

        with open(os.path.join(self.repo, "conf.txt"), "w", encoding="utf-8") as f:
            f.write("ours\n")
        self.g.add(["."])
        self.g.commit("ours change")

        # 拉取并合并 → 冲突
        out, err, code = _git(self.repo, "pull", "origin", "main")
        self.assertNotEqual(code, 0, f"pull 应冲突失败: {err}")
        items = self.g.status_items()
        conflict = [i for i in items if i["status"] in cards._CONFLICT_STATUS]
        self.assertEqual(len(conflict), 1, f"items={items}")
        self.assertEqual(conflict[0]["path"], "conf.txt")

        # 冲突解决：ours
        self.assertTrue(self.g.checkout_ours("conf.txt").ok)
        with open(os.path.join(self.repo, "conf.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "ours\n")
        self.assertTrue(self.g.add(["conf.txt"]).ok)


class TestDiffRenderer(unittest.TestCase):
    def test_word_level_highlight(self):
        diff = (
            "diff --git a/f.txt b/f.txt\n"
            "index 111..222 100644\n"
            "--- a/f.txt\n"
            "+++ b/f.txt\n"
            "@@ -1 +1 @@\n"
            "-hello world\n"
            "+hello brave world\n"
        )
        html = diff_renderer.render_diff_html(diff)
        # 行级颜色
        self.assertIn("color:#50e3c2", html)
        self.assertIn("color:#f14c4c", html)
        # 词级高亮：'brave' 是新增词 → 浅绿底
        self.assertIn("rgba(80,227,194,0.28)", html)
        self.assertIn("brave", html)
        # 'world' 公共词不加高亮底
        self.assertLessEqual(html.count("rgba(80,227,194,0.28)"), 1)

    def test_html_escape(self):
        diff = "-a < b & c\n+a > b\n"
        html = diff_renderer.render_diff_html(diff)
        self.assertNotIn("< b", html)
        self.assertIn("&lt;", html)
        self.assertIn("&amp;", html)

    def test_plain_text(self):
        html = diff_renderer.render_plain_text("hello\nworld")
        self.assertIn("hello", html)
        self.assertIn("world", html)


class TestCommitDetailParse(unittest.TestCase):
    def test_parse_show_output(self):
        text = (
            "commit abc123def456\n"
            "Author:     Tester <t@t.t>\n"
            "AuthorDate: Mon Jan 1 00:00:00 2024 +0800\n"
            "Commit:     Tester <t@t.t>\n"
            "CommitDate: Mon Jan 1 00:00:00 2024 +0800\n"
            "\n"
            "    feat: something\n"
            "    \n"
            "    body line\n"
            "\n"
            " a.txt | 1 +\n"
            " 1 file changed, 1 insertion(+)\n"
            "\n"
            "diff --git a/a.txt b/a.txt\n"
            "index 111..222 100644\n"
            "--- a/a.txt\n"
            "+++ b/a.txt\n"
            "@@ -0,0 +1 @@\n"
            "+x\n"
        )
        info = cards._CommitDetailDialog._parse_show_output(text)
        self.assertEqual(info["hash"], "abc123def456")
        self.assertEqual(info["author"], "Tester <t@t.t>")
        self.assertEqual(info["date"], "Mon Jan 1 00:00:00 2024 +0800")
        self.assertIn("feat: something", info["message"])
        self.assertIn("body line", info["message"])
        self.assertTrue(info["diff"].startswith("diff --git"))


class TestReviewFixes(TempRepoMixin, unittest.TestCase):
    """P0 code review 反馈修复的针对性测试"""

    def test_error_message_fallback(self):
        """Q4：stderr 为空时返回固定字符串，不回退 stdout"""
        res = cards.GitResult(ok=False, stdout="some stdout", stderr="")
        self.assertEqual(res.error_message, "未知错误（stderr 为空）")
        res2 = cards.GitResult(ok=False, stdout="", stderr="fatal: boom")
        self.assertEqual(res2.error_message, "fatal: boom")

    def test_pull_rebase_conflict_returns_original(self):
        """M3：rebase 冲突时返回原错误，不静默回退普通 pull"""
        bare = os.path.join(self._tmp, "remote.git")
        subprocess.run(["git", "init", "--bare", "-b", "main", bare],
                       capture_output=True, text=True)
        _git(self.repo, "config", "user.email", "t@t.t")
        _git(self.repo, "config", "user.name", "T")
        self._write("f.txt", "base\n")
        self.g.add(["."])
        self.g.commit("base")
        _git(self.repo, "remote", "add", "origin", bare)
        self.assertTrue(self.g.push().ok)

        clone = os.path.join(self._tmp, "clone")
        subprocess.run(["git", "clone", bare, clone], capture_output=True, text=True)
        _git(clone, "config", "user.email", "t@t.t")
        _git(clone, "config", "user.name", "T")
        with open(os.path.join(clone, "f.txt"), "w", encoding="utf-8") as f:
            f.write("theirs\n")
        _git(clone, "add", "-A")
        _git(clone, "commit", "-m", "theirs")
        _git(clone, "push")

        with open(os.path.join(self.repo, "f.txt"), "w", encoding="utf-8") as f:
            f.write("ours\n")
        self.g.add(["."])
        self.g.commit("ours")

        res = self.g.pull_rebase()
        self.assertFalse(res.ok, "rebase 冲突应返回失败")
        self.assertIn("conflict", res.stderr.lower())

    def test_push_upstream_retry_keyword(self):
        """M2：无 upstream 时按 stderr 关键字重试成功"""
        bare = os.path.join(self._tmp, "remote.git")
        subprocess.run(["git", "init", "--bare", "-b", "main", bare],
                       capture_output=True, text=True)
        _git(self.repo, "config", "user.email", "t@t.t")
        _git(self.repo, "config", "user.name", "T")
        self._write("f.txt", "x\n")
        self.g.add(["."])
        self.g.commit("c")
        _git(self.repo, "remote", "add", "origin", bare)
        # 无 upstream 直接 push → 应通过 --set-upstream 重试成功
        res = self.g.push()
        self.assertTrue(res.ok, res.error_message)
        ahead, behind = self.g.ahead_behind()
        self.assertEqual((ahead, behind), (0, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
