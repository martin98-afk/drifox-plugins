# -*- coding: utf-8 -*-
"""
hashline-edit 插件单元测试（纯标准库，无 DriFox 依赖）

覆盖（完成标准 2）：
- 哈希稳定性 / 上下文区分 / 编辑行 N 只影响 N-1/N/N+1 锚点
- 锚点解析（合法/非法）
- 编辑应用（replace/append/prepend/replace_text 自底向上）
- 陈旧锚点拒绝（E_STALE_ANCHOR，hash 级与 mtime 级两条路径）
- 注入内容拒绝（E_INVALID_PATCH）
- no-op 循环检测（E_NOOP_LOOP）
- multi_edit 多编辑点 / 区间 replace / 链式锚点块
- read/edit 全流程集成（锚点输出 + diff + 链式续编）
"""
import importlib.util
import html
import os
import re
import sys
import types
from pathlib import Path

import pytest

_PLUGIN_TOOLS = Path(__file__).resolve().parent.parent / "plugins" / "hashline-edit" / "tools"

_ANCHOR_LINE_RE = re.compile(r"^(\d+)#([ZPMQVRWSNKTXJBYH]{2,4}): (.*)$")


# ========== app.* stub（模拟主程序依赖，纯标准库可跑） ==========


def _make_app_stubs():
    if "app" in sys.modules:
        return
    app = types.ModuleType("app")
    tools = types.ModuleType("app.tools")
    result_mod = types.ModuleType("app.tools.result")
    registry_mod = types.ModuleType("app.tools.registry")

    class ToolResult:
        def __init__(self, success, content=None, error=None, diff=None,
                     anchors=None, echarts=None, image_data=None, todos=None):
            self.success = success
            self.content = content
            self.error = error
            self.diff = diff
            self.anchors = anchors
            self.echarts = echarts
            self.image_data = image_data
            self.todos = todos

        def to_dict(self):
            d = {"success": self.success}
            if self.success:
                d["content"] = self.content
            else:
                d["error"] = self.error
            if self.diff:
                d["diff"] = self.diff
            if self.anchors:
                d["anchors"] = self.anchors
            if self.image_data:
                d["image_data"] = self.image_data
            return d

    def make_summarize_from_preview(preview_fn):
        def _summarize(name, args, content):
            label = preview_fn(args or {}) if preview_fn else ""
            return f"[{name}] {label} ({len(content or '')} chars)"

        return _summarize

    result_mod.ToolResult = ToolResult
    registry_mod.make_summarize_from_preview = make_summarize_from_preview
    tools.result = result_mod
    tools.registry = registry_mod
    app.tools = tools
    sys.modules["app"] = app
    sys.modules["app.tools"] = tools
    sys.modules["app.tools.result"] = result_mod
    sys.modules["app.tools.registry"] = registry_mod


def _load(name: str, filename: str):
    if name in sys.modules:
        return sys.modules[name]
    path = _PLUGIN_TOOLS / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_make_app_stubs()
if str(_PLUGIN_TOOLS) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_TOOLS))

engine = _load("hashline_engine", "hashline_engine.py")
file_io = _load("file_io", "file_io.py")
snapshot = _load("snapshot", "snapshot.py")
read_tool = _load("read_tool", "read_tool.py")
edit_tool = _load("edit_tool", "edit_tool.py")


# ---- render 闭包依赖的 app.widgets.render_helpers stub（render 闭包 lazy import） ----

def _make_render_helpers_stub():
    if "app.widgets" in sys.modules:
        return
    widgets = types.ModuleType("app.widgets")
    rh = types.ModuleType("app.widgets.render_helpers")

    def _summarize_diff(diff_text):
        added = deleted = 0
        files = []
        for line in diff_text.splitlines():
            if line.startswith("--- "):
                files.append(line[4:])
            elif line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                deleted += 1
        return {"added": added, "deleted": deleted, "files": files}

    def _render_diff_preview(diff_text):
        rows = []
        for line in diff_text.splitlines():
            kind = "ctx"
            if line.startswith("@@"):
                kind = "hunk"
            elif line.startswith("+") and not line.startswith("+++"):
                kind = "add"
            elif line.startswith("-") and not line.startswith("---"):
                kind = "del"
            rows.append(f'<div class="diff-line diff-{kind}">{line}</div>')
        return '<div class="diff-body">' + "".join(rows) + "</div>"

    rh._summarize_diff = _summarize_diff
    rh._render_diff_preview = _render_diff_preview
    rh._get_global_font = lambda: "Segoe UI"
    rh.escape = html.escape
    rh.get_font_family_css = lambda: "font-family: 'Segoe UI';"
    rh.scale_font_size = lambda n: n
    widgets.render_helpers = rh
    sys.modules["app.widgets"] = widgets
    sys.modules["app.widgets.render_helpers"] = rh


_make_render_helpers_stub()


class FakeWindowState(dict):
    """模拟 services.window_state：ws['get'] / ws['set'] / ws['delete']"""

    def __getitem__(self, key):
        if key in ("get", "set", "delete"):
            return getattr(self, key)
        return super().__getitem__(key)

    def get(self, k, default=None):
        return super().get(k, default)

    def set(self, k, v):
        super().__setitem__(k, v)

    def delete(self, k):
        self.pop(k, None)


def make_ctx(tmp_path, ws=None):
    return {"workdir": str(tmp_path), "services": {"window_state": ws or FakeWindowState()}}


def write_file(tmp_path, text: str, name: str = "t.txt"):
    f = tmp_path / name
    f.write_text(text, encoding="utf-8")
    return f


def read_pos(result, lineno: int) -> str:
    """从 read 输出提取第 lineno 行的锚点（LINE#HASH）"""
    body = result.content.split("\n")[1:]
    for line in body:
        m = _ANCHOR_LINE_RE.match(line)
        if m and int(m.group(1)) == lineno:
            return f"{m.group(1)}#{m.group(2)}"
    raise AssertionError(f"第 {lineno} 行锚点未找到: {result.content!r}")


# ========== 1. 哈希机制 ==========


class TestHash:
    def test_hash_stability(self):
        h1 = engine.context_hash("a", "b", "c")
        h2 = engine.context_hash("a", "b", "c")
        assert h1 == h2
        assert len(h1) == engine.DEFAULT_WIDTH == 2

    def test_hash_width_range(self):
        for w in (2, 3, 4):
            h = engine.context_hash("x", "y", "z", width=w)
            assert len(h) == w
            assert all(c in engine.ALPHABET for c in h)
        # 越界钳制
        assert len(engine.context_hash("x", "y", "z", width=1)) == 2
        assert len(engine.context_hash("x", "y", "z", width=9)) == 4

    def test_hash_context_distinct(self):
        """相同行不同上下文 → 不同 hash"""
        a = engine.context_hash("p1", "SAME", "n1")
        b = engine.context_hash("p2", "SAME", "n1")
        c = engine.context_hash("p1", "SAME", "n2")
        assert a != b
        assert a != c

    def test_hash_content_distinct(self):
        """相同上下文不同行内容 → 不同 hash"""
        assert engine.context_hash("p", "AAA", "n") != engine.context_hash("p", "BBB", "n")

    def test_hash_local_impact(self):
        """编辑行 N 只影响 N-1/N/N+1 锚点（三行窗口局部性）"""
        lines = [f"line{i}" for i in range(1, 8)]
        before = engine.hash_all(lines)
        modified = list(lines)
        modified[2] = "CHANGED"  # 编辑第 3 行（0 起始 idx=2）
        after = engine.hash_all(modified)
        changed = [i for i in range(len(lines)) if before[i] != after[i]]
        assert changed == [1, 2, 3]  # 0 起始：第 2/3/4 行（1 起始）

    def test_hash_line_boundary(self):
        """边界行（首/尾）hash 稳定，缺行按空串"""
        lines = ["first", "mid", "last"]
        hs = engine.hash_all(lines)
        assert len(hs) == 3
        assert engine.line_hash(lines, 0) == engine.context_hash("", "first", "mid")
        assert engine.line_hash(lines, 2) == engine.context_hash("mid", "last", "")


class TestAnchorParse:
    def test_parse_valid(self):
        assert engine.parse_anchor("9#KT") == (9, "KT")
        assert engine.parse_anchor("1#ZM") == (1, "ZM")
        assert engine.parse_anchor(" 123#ZMT ") == (123, "ZMT")

    def test_parse_invalid(self):
        for bad in ("", "9", "#KT", "9#", "9#k", "9#K", "9#K1", "abc#KT", "0#KT", "-1#KT"):
            with pytest.raises(ValueError):
                engine.parse_anchor(bad)

    def test_format_line(self):
        assert engine.format_line(9, "KT", "hello") == "9#KT: hello"
        assert engine.format_line(5, "ZM", "") == "5#ZM: "

    def test_format_anchors_block(self):
        lines = ["a", "b", "c"]
        hs = engine.hash_all(lines)
        block = engine.format_anchors_block(1, 3, lines, hs)
        assert block.splitlines()[0] == "--- Anchors 1-3 ---"
        assert len(block.splitlines()) == 4
        # 越界裁剪
        block2 = engine.format_anchors_block(1, 99, lines, hs)
        assert block2.splitlines()[0] == "--- Anchors 1-3 ---"


# ========== 2. 编辑应用（bottom-up） ==========


class TestApplyEdits:
    def test_replace_single(self):
        lines = ["a", "b", "c"]
        hs = engine.hash_all(lines)
        new, meta = snapshot.apply_edits(lines, [
            {"op": "replace", "anchor": f"2#{hs[1]}", "lines": ["B"]},
        ])
        assert not meta["errors"]
        assert new == ["a", "B", "c"]
        assert meta["noop"] is False
        assert meta["affected"] == (1, 3)

    def test_append_prepend(self):
        lines = ["a", "b", "c"]
        hs = engine.hash_all(lines)
        new, meta = snapshot.apply_edits(lines, [
            {"op": "append", "anchor": f"1#{hs[0]}", "content": "!"},
            {"op": "prepend", "anchor": f"3#{hs[2]}", "content": ">> "},
        ])
        assert not meta["errors"]
        assert new == ["a!", "b", ">> c"]

    def test_replace_text(self):
        lines = ["def foo(x): return x", "y = 1"]
        hs = engine.hash_all(lines)
        new, meta = snapshot.apply_edits(lines, [
            {"op": "replace_text", "anchor": f"1#{hs[0]}",
             "content": '{"old": "foo", "new": "bar"}'},
        ])
        assert not meta["errors"]
        assert new[0] == "def bar(x): return x"
        assert new[1] == "y = 1"

    def test_bottom_up_order(self):
        """自底向上：先应用高行号，低行号插入不破坏后续编辑定位"""
        lines = ["a", "b", "c"]
        hs = engine.hash_all(lines)
        new, meta = snapshot.apply_edits(lines, [
            {"op": "replace", "anchor": f"1#{hs[0]}", "lines": ["x", "y"]},  # 行 1 插入两行
            {"op": "replace", "anchor": f"3#{hs[2]}", "lines": ["Z"]},      # 行 3 基于 pre-edit
        ])
        assert not meta["errors"]
        assert new == ["x", "y", "b", "Z"]  # 若顺序错会得 ["x","y","Z","c"]

    def test_range_replace(self):
        """区间 replace：删除/替换 [pos, end] 多行"""
        lines = ["a", "b", "c", "d", "e"]
        hs = engine.hash_all(lines)
        new, meta = snapshot.apply_edits(lines, [
            {"op": "replace", "anchor": f"2#{hs[1]}", "end": f"4#{hs[3]}", "lines": ["BB"]},
        ])
        assert not meta["errors"]
        assert new == ["a", "BB", "e"]

    def test_range_replace_delete(self):
        lines = ["a", "b", "c", "d", "e"]
        hs = engine.hash_all(lines)
        new, meta = snapshot.apply_edits(lines, [
            {"op": "replace", "anchor": f"2#{hs[1]}", "end": f"4#{hs[3]}", "lines": []},
        ])
        assert not meta["errors"]
        assert new == ["a", "e"]

    def test_noop_detection(self):
        lines = ["a", "b", "c"]
        hs = engine.hash_all(lines)
        new, meta = snapshot.apply_edits(lines, [
            {"op": "replace", "anchor": f"2#{hs[1]}", "lines": ["b"]},  # 与原行相同
        ])
        assert not meta["errors"]
        assert meta["noop"] is True
        assert new == lines

    def test_validate_injection_lines(self):
        """lines 含锚点前缀 / diff 标记 → E_INVALID_PATCH"""
        lines = ["a", "b", "c"]
        hs = engine.hash_all(lines)
        for bad_lines in (["9#KT: x"], ["+ new"], ["- old"], ["@@ -1 +1 @@"]):
            new, meta = snapshot.apply_edits(lines, [
                {"op": "replace", "anchor": f"2#{hs[1]}", "lines": bad_lines},
            ])
            assert meta["errors"], f"应拒绝: {bad_lines!r}"
            assert snapshot.E_INVALID_PATCH in meta["errors"][0]
            assert new == lines  # 不写文件

    def test_validate_injection_content(self):
        lines = ["a", "b", "c"]
        hs = engine.hash_all(lines)
        # content 含换行（跨行操作）→ 拒绝
        new, meta = snapshot.apply_edits(lines, [
            {"op": "append", "anchor": f"2#{hs[1]}", "content": "x\ny"},
        ])
        assert meta["errors"] and snapshot.E_INVALID_PATCH in meta["errors"][0]
        # content 含 diff 标记 → 拒绝
        new, meta = snapshot.apply_edits(lines, [
            {"op": "prepend", "anchor": f"2#{hs[1]}", "content": "- "},
        ])
        assert meta["errors"] and snapshot.E_INVALID_PATCH in meta["errors"][0]

    def test_replace_text_old_not_unique(self):
        lines = ["x = x + 1  # comment", "y = 2"]
        hs = engine.hash_all(lines)
        new, meta = snapshot.apply_edits(lines, [
            {"op": "replace_text", "anchor": f"1#{hs[0]}",
             "content": '{"old": "x", "new": "z"}'},  # x 出现多次
        ])
        assert meta["errors"] and snapshot.E_INVALID_PATCH in meta["errors"][0]

    def test_unknown_op(self):
        lines = ["a", "b"]
        hs = engine.hash_all(lines)
        new, meta = snapshot.apply_edits(lines, [
            {"op": "delete_line", "anchor": f"1#{hs[0]}"},
        ])
        assert meta["errors"] and snapshot.E_INVALID_PATCH in meta["errors"][0]

    def test_all_or_nothing(self):
        """多编辑点任一失败 → 整体拒绝，不部分应用"""
        lines = ["a", "b", "c"]
        hs = engine.hash_all(lines)
        new, meta = snapshot.apply_edits(lines, [
            {"op": "replace", "anchor": f"1#{hs[0]}", "lines": ["A"]},
            {"op": "replace", "anchor": "3#ZZ", "lines": ["C"]},  # 陈旧锚点
        ])
        assert meta["errors"] and snapshot.E_STALE_ANCHOR in meta["errors"][0]
        assert new == lines


# ========== 3. 陈旧锚点 / no-op 循环 ==========


class TestStaleAnchor:
    def test_stale_hash_rejected(self):
        """锚点 hash 不匹配 → E_STALE_ANCHOR（hash 级校验）"""
        lines = ["a", "b", "c"]
        hs = engine.hash_all(lines)
        new, meta = snapshot.apply_edits(lines, [
            {"op": "replace", "anchor": f"2#{hs[1][0]}{'X' if hs[1][1] != 'X' else 'Y'}", "lines": ["B"]},
        ])
        assert meta["errors"] and snapshot.E_STALE_ANCHOR in meta["errors"][0]
        assert new == lines

    def test_stale_lineno_out_of_range(self):
        lines = ["a", "b"]
        hs = engine.hash_all(lines)
        new, meta = snapshot.apply_edits(lines, [
            {"op": "replace", "anchor": f"9#{hs[0]}", "lines": ["X"]},
        ])
        assert meta["errors"] and snapshot.E_STALE_ANCHOR in meta["errors"][0]

    def test_text_hint_second_factor(self):
        lines = ["keep", "target", "tail"]
        hs = engine.hash_all(lines)
        new, meta = snapshot.apply_edits(lines, [
            {"op": "replace", "anchor": f"2#{hs[1]}", "lines": ["NEW"], "textHint": "target"},
        ])
        assert not meta["errors"] and new == ["keep", "NEW", "tail"]
        # textHint 不匹配 → 拒绝
        new, meta = snapshot.apply_edits(lines, [
            {"op": "replace", "anchor": f"2#{hs[1]}", "lines": ["NEW"], "textHint": "WRONG"},
        ])
        assert meta["errors"] and snapshot.E_STALE_ANCHOR in meta["errors"][0]


class TestNoopLoop:
    def test_noop_loop_detected(self):
        """连续 3 次相同 no-op → E_NOOP_LOOP"""
        ws = FakeWindowState()
        ctx = make_ctx(None, ws)
        tmp = ctx["workdir"] and Path(ctx["workdir"]) or Path(".")
        fake_path = tmp / "x.txt"
        sig = '{"op": "replace"}'
        assert snapshot.note_noop(ctx, fake_path, sig) is None        # 第 1 次：允许
        assert snapshot.note_noop(ctx, fake_path, sig) is None        # 第 2 次：允许
        err = snapshot.note_noop(ctx, fake_path, sig)                 # 第 3 次：报错
        assert err and snapshot.E_NOOP_LOOP in err
        # 不同 sig 重置计数
        assert snapshot.note_noop(ctx, fake_path, "other-sig") is None

    def test_success_edit_resets_noop(self):
        ws = FakeWindowState()
        ctx = make_ctx(None, ws)
        fake_path = Path("y.txt")
        sig = "same"
        snapshot.note_noop(ctx, fake_path, sig)
        snapshot.note_noop(ctx, fake_path, sig)
        snapshot.reset_noop(ctx, fake_path)
        assert snapshot.note_noop(ctx, fake_path, sig) is None  # 重置后重新计数


# ========== 4. read / edit 全流程集成 ==========


class TestReadTool:
    def test_read_anchor_output(self, tmp_path):
        write_file(tmp_path, "a\nb\nc\n")
        ctx = make_ctx(tmp_path)
        r = read_tool._read_impl(ctx, path="t.txt")
        assert r.success
        assert r.content.startswith("#File: t.txt (Lines 1-3 of 3)")
        lines = r.content.split("\n")[1:]
        assert len(lines) == 3
        for i, line in enumerate(lines, 1):
            m = _ANCHOR_LINE_RE.match(line)
            assert m, f"锚点格式错误: {line!r}"
            assert int(m.group(1)) == i
            assert m.group(3) == ["a", "b", "c"][i - 1]

    def test_read_partial_with_context(self, tmp_path):
        """分段读取：边界行 hash 依赖真实上下文行"""
        write_file(tmp_path, "\n".join(f"L{i}" for i in range(1, 7)) + "\n")
        ctx = make_ctx(tmp_path)
        r = read_tool._read_impl(ctx, path="t.txt", startline=2, endline=4)
        assert r.success
        lines = r.content.split("\n")[1:]
        assert len(lines) == 3
        assert int(_ANCHOR_LINE_RE.match(lines[0]).group(1)) == 2
        assert _ANCHOR_LINE_RE.match(lines[0]).group(3) == "L2"
        # 行 2 的 hash 应等于全量计算的 line_hash
        all_lines = ["L1", "L2", "L3", "L4", "L5", "L6"]
        assert _ANCHOR_LINE_RE.match(lines[0]).group(2) == engine.line_hash(all_lines, 1)

    def test_read_missing_file(self, tmp_path):
        ctx = make_ctx(tmp_path)
        r = read_tool._read_impl(ctx, path="nope.txt")
        assert not r.success and "not found" in r.error

    def test_read_directory_lists(self, tmp_path):
        """目录 → 自动转 list 列目录（与系统 read 行为一致）"""
        (tmp_path / "sub").mkdir()
        (tmp_path / "a.txt").write_text("x", encoding="utf-8")
        ctx = make_ctx(tmp_path)
        r = read_tool._read_impl(ctx, path=".")
        assert r.success, r.error
        assert r.content.startswith("目录: ")
        assert "[DIR] sub" in r.content  # 目录在前、[DIR] 标记
        assert "a.txt" in r.content

    def test_read_directory_relative(self, tmp_path):
        """相对目录路径同样转 list"""
        (tmp_path / "sub").mkdir()
        ctx = make_ctx(tmp_path)
        r = read_tool._read_impl(ctx, path="sub")
        assert r.success
        assert r.content.startswith("目录: ") and "sub" in r.content

    def test_read_image_protocol(self, tmp_path):
        png = bytes.fromhex("89504e470d0a1a0a00000000")  # 最小 PNG 头（含魔数即可）
        (tmp_path / "img.png").write_bytes(png)
        ctx = make_ctx(tmp_path)
        r = read_tool._read_impl(ctx, path="img.png")
        assert r.success
        assert r.image_data and r.image_data["mime"] == "image/png"
        assert r.image_data["data"]

    def test_show_line_numbers_ignored(self, tmp_path):
        write_file(tmp_path, "a\nb\n")
        ctx = make_ctx(tmp_path)
        r = read_tool._read_impl(ctx, path="t.txt", show_line_numbers=True)
        assert r.success
        assert _ANCHOR_LINE_RE.match(r.content.split("\n")[1])  # 仍为锚点格式


class TestEditFlow:
    def test_edit_full_flow(self, tmp_path):
        """read → edit（replace）→ diff + 链式锚点块 → 文件已更新"""
        write_file(tmp_path, "a\nb\nc\n")
        ctx = make_ctx(tmp_path)
        r1 = read_tool._read_impl(ctx, path="t.txt")
        pos = read_pos(r1, 2)
        r2 = edit_tool._edit_impl(ctx, path="t.txt", operations=[
            {"op": "replace", "anchor": pos, "lines": ["B2"]},
        ])
        assert r2.success, r2.error
        assert "B2" in (r2.diff or "")
        assert r2.anchors and r2.anchors.startswith("--- Anchors")
        assert (tmp_path / "t.txt").read_text(encoding="utf-8") == "a\nB2\nc\n"

    def test_chained_edit(self, tmp_path):
        """链式编辑：用 edit 返回的新锚点继续编辑"""
        write_file(tmp_path, "a\nb\nc\n")
        ctx = make_ctx(tmp_path)
        r1 = read_tool._read_impl(ctx, path="t.txt")
        r2 = edit_tool._edit_impl(ctx, path="t.txt", operations=[
            {"op": "replace", "anchor": read_pos(r1, 2), "lines": ["B2"]},
        ])
        # 从新锚点块取行 3 的锚点继续编辑
        anchor_line3 = [ln for ln in r2.anchors.split("\n") if ln.startswith("3#")][0]
        pos3 = anchor_line3.split(":")[0]
        r3 = edit_tool._edit_impl(ctx, path="t.txt", operations=[
            {"op": "append", "anchor": pos3, "content": "!"},
        ])
        assert r3.success, r3.error
        assert (tmp_path / "t.txt").read_text(encoding="utf-8") == "a\nB2\nc!\n"

    def test_multi_edit_multiple_points(self, tmp_path):
        write_file(tmp_path, "a\nb\nc\nd\n")
        ctx = make_ctx(tmp_path)
        r1 = read_tool._read_impl(ctx, path="t.txt")
        r2 = edit_tool._multi_edit_impl(ctx, path="t.txt", operations=[
            {"op": "replace", "anchor": read_pos(r1, 1), "lines": ["A1"]},
            {"op": "prepend", "anchor": read_pos(r1, 3), "content": ">> "},
            {"op": "replace_text", "anchor": read_pos(r1, 4),
             "content": '{"old": "d", "new": "D4"}'},
        ])
        assert r2.success, r2.error
        assert (tmp_path / "t.txt").read_text(encoding="utf-8") == "A1\nb\n>> c\nD4\n"
        assert "3 处" in r2.content

    def test_edit_stale_anchor(self, tmp_path):
        """内容变化（mtime 恢复）→ 旧锚点 hash 不匹配 → E_STALE_ANCHOR"""
        f = write_file(tmp_path, "a\nb\nc\n")
        ctx = make_ctx(tmp_path)
        r1 = read_tool._read_impl(ctx, path="t.txt")
        pos = read_pos(r1, 2)
        st = f.stat()
        old_mtime = st.st_mtime
        f.write_text("a\nCHANGED\nc\n", encoding="utf-8")
        os.utime(f, (st.st_atime, old_mtime))  # 恢复 mtime，绕过外部修改检测
        r2 = edit_tool._edit_impl(ctx, path="t.txt", operations=[
            {"op": "replace", "anchor": pos, "lines": ["B2"]},
        ])
        assert not r2.success
        assert snapshot.E_STALE_ANCHOR in r2.error

    def test_edit_external_modified_mtime(self, tmp_path):
        """read 后外部修改（mtime 变化）→ 拒绝编辑"""
        f = write_file(tmp_path, "a\nb\nc\n")
        ctx = make_ctx(tmp_path)
        r1 = read_tool._read_impl(ctx, path="t.txt")
        pos = read_pos(r1, 2)
        f.write_text("a\nb\nc\nd\n", encoding="utf-8")  # mtime 变化
        r2 = edit_tool._edit_impl(ctx, path="t.txt", operations=[
            {"op": "replace", "anchor": pos, "lines": ["B2"]},
        ])
        assert not r2.success
        assert "外部修改" in r2.error

    def test_edit_noop_loop_via_tool(self, tmp_path):
        """工具级 no-op：连续 3 次相同 no-op 编辑 → E_NOOP_LOOP"""
        ws = FakeWindowState()
        write_file(tmp_path, "a\nb\nc\n")
        ctx = make_ctx(tmp_path, ws)
        r1 = read_tool._read_impl(ctx, path="t.txt")
        pos = read_pos(r1, 2)
        for i in range(2):
            r = edit_tool._edit_impl(ctx, path="t.txt", operations=[
                {"op": "replace", "anchor": pos, "lines": ["b"]},  # 与原行相同 → no-op
            ])
            assert r.success and "no-op" in r.content
        r3 = edit_tool._edit_impl(ctx, path="t.txt", operations=[
            {"op": "replace", "anchor": pos, "lines": ["b"]},
        ])
        assert not r3.success
        assert snapshot.E_NOOP_LOOP in r3.error

    def test_edit_invalid_patch_via_tool(self, tmp_path):
        write_file(tmp_path, "a\nb\nc\n")
        ctx = make_ctx(tmp_path)
        r1 = read_tool._read_impl(ctx, path="t.txt")
        pos = read_pos(r1, 2)
        r2 = edit_tool._edit_impl(ctx, path="t.txt", operations=[
            {"op": "replace", "anchor": pos, "lines": ["2#XX: b"]},  # 锚点前缀注入
        ])
        assert not r2.success
        assert snapshot.E_INVALID_PATCH in r2.error
        # 文件未被破坏
        assert (tmp_path / "t.txt").read_text(encoding="utf-8") == "a\nb\nc\n"

    def test_edit_unknown_file(self, tmp_path):
        ctx = make_ctx(tmp_path)
        r = edit_tool._edit_impl(ctx, path="missing.txt", operations=[
            {"op": "replace", "anchor": "1#ZZ", "lines": ["x"]},
        ])
        assert not r.success and "not found" in r.error

    def test_edit_bad_anchor_format(self, tmp_path):
        write_file(tmp_path, "a\nb\n")
        ctx = make_ctx(tmp_path)
        r = edit_tool._edit_impl(ctx, path="t.txt", operations=[
            {"op": "replace", "anchor": "not-an-anchor", "lines": ["x"]},
        ])
        assert not r.success
        assert snapshot.E_INVALID_PATCH in r.error

    def test_diff_present(self, tmp_path):
        write_file(tmp_path, "a\nb\nc\n")
        ctx = make_ctx(tmp_path)
        r1 = read_tool._read_impl(ctx, path="t.txt")
        r2 = edit_tool._edit_impl(ctx, path="t.txt", operations=[
            {"op": "replace", "anchor": read_pos(r1, 1), "lines": ["A"]},
        ])
        assert r2.success
        assert "---" in (r2.diff or "")  # unified diff 头
        assert "+A" in r2.diff
        assert "-a" in r2.diff


class TestRenderDiff:
    """render 闭包与系统 _render_edit_diff_body 同款结构（差异框渲染）"""

    def test_render_diff_body_structure(self, tmp_path):
        write_file(tmp_path, "a\nb\nc\n")
        ctx = make_ctx(tmp_path)
        r1 = read_tool._read_impl(ctx, path="t.txt")
        r2 = edit_tool._edit_impl(ctx, path="t.txt", operations=[
            {"op": "replace", "anchor": read_pos(r1, 1), "lines": ["A"]},
        ])
        assert r2.success and r2.diff
        h = edit_tool._render_diff_body(r2, "edit", {"path": "t.txt"}, True)
        assert h and 'class="tool-diff-inline"' in h
        assert "tool-diff-inline__header" in h
        assert "tool-diff-inline__file" in h and "t.txt" in h  # 文件标签
        assert "tool-diff-inline__summary" in h
        assert "tool-diff-inline__add" in h and "+1" in h       # +N 统计
        assert "tool-diff-inline__del" in h and "-1" in h       # -N 统计
        assert "tool-diff-inline__body" in h
        assert 'diff-add' in h  # _render_diff_preview 输出（stub 保留类名）
        assert 'diff-del' in h

    def test_render_diff_body_no_diff_returns_none(self):
        """无 diff → 返回 None（渲染层回退通用渲染，与系统行为一致）"""
        from app.tools.result import ToolResult

        r = ToolResult(True, content="x")
        assert edit_tool._render_diff_body(r, "edit", {}, True) is None
        r2 = ToolResult(False, error="e")
        assert edit_tool._render_diff_body(r2, "edit", {}, False) is None

    def test_render_diff_body_multiple_files_label(self):
        from app.tools.result import ToolResult

        diff = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n" \
               "--- a/y.py\n+++ b/y.py\n@@ -1 +1 @@\n-old\n+new\n"
        r = ToolResult(True, content="ok", diff=diff)
        h = edit_tool._render_diff_body(r, "edit", {"path": "x.py"}, True)
        assert "x.py 等 2 个文件" in h
        assert "+2" in h and "-2" in h

    def test_render_diff_failure_note_shown(self):
        """success=False + diff 非空 → 错误详情输出为提示块（不被 diff 吞掉）"""
        from app.tools.result import ToolResult

        diff = "--- a/t.txt\n+++ b/t.txt\n@@ -1 +1 @@\n-old\n+new\n"
        r = ToolResult(False, error="E_STALE_ANCHOR: 锚点已过期", diff=diff)
        h = edit_tool._render_diff_body(r, "edit", {"path": "t.txt"}, False)
        assert h and "tool-diff-inline__note" in h
        assert "E_STALE_ANCHOR" in h

    def test_render_diff_success_no_note(self):
        """全部成功 → 不输出提示块（无失败关键词，与系统行为一致）"""
        from app.tools.result import ToolResult

        diff = "--- a/t.txt\n+++ b/t.txt\n@@ -1 +1 @@\n-old\n+new\n"
        r = ToolResult(True, content="已编辑 t.txt（1 处锚点编辑成功）", diff=diff)
        h = edit_tool._render_diff_body(r, "edit", {"path": "t.txt"}, True)
        assert h and "tool-diff-inline__note" not in h


class TestDegradedNoWindowState:
    """Block-2：无 window_state 时降级路径不崩溃（模块级状态兜底）"""

    def _no_ws_ctx(self):
        # 无 services.window_state → file_io/snapshot 走模块级降级
        return {"workdir": ".", "services": {}}

    def test_noop_detection_degraded(self):
        """no-op 计数降级路径：连续 3 次 → E_NOOP_LOOP（不抛 AttributeError）"""
        ctx = self._no_ws_ctx()
        fake_path = Path("deg_noop_x.txt")  # 独立路径，避免污染其他用例
        sig = '{"op": "replace"}'
        assert snapshot.note_noop(ctx, fake_path, sig) is None        # 第 1 次
        assert snapshot.note_noop(ctx, fake_path, sig) is None        # 第 2 次
        err = snapshot.note_noop(ctx, fake_path, sig)                 # 第 3 次 → 报错
        assert err and snapshot.E_NOOP_LOOP in err
        # 不同 sig 重置
        assert snapshot.note_noop(ctx, fake_path, "other-sig") is None

    def test_noop_reset_degraded(self):
        ctx = self._no_ws_ctx()
        fake_path = Path("deg_noop_y.txt")
        snapshot.note_noop(ctx, fake_path, "s")
        snapshot.note_noop(ctx, fake_path, "s")
        snapshot.reset_noop(ctx, fake_path)
        assert snapshot.note_noop(ctx, fake_path, "s") is None  # 重置后重新计数

    def test_mtime_degraded(self, tmp_path):
        """mtime 记录/外部修改检测降级路径（无 window_state）"""
        f = write_file(tmp_path, "a\nb\nc\n", name="deg_mtime.txt")
        ctx = {"workdir": str(tmp_path), "services": {}}
        r1 = read_tool._read_impl(ctx, path="deg_mtime.txt")
        assert r1.success
        pos = read_pos(r1, 2)
        # 外部修改（内容变 + mtime 变）→ 拒绝
        f.write_text("a\nCHANGED\nc\n", encoding="utf-8")
        r2 = edit_tool._edit_impl(ctx, path="deg_mtime.txt", operations=[
            {"op": "replace", "anchor": pos, "lines": ["B2"]},
        ])
        assert not r2.success
        assert "外部修改" in r2.error
        # 重新 read 后正常编辑（降级状态可写）
        r3 = read_tool._read_impl(ctx, path="deg_mtime.txt")
        pos2 = read_pos(r3, 2)
        r4 = edit_tool._edit_impl(ctx, path="deg_mtime.txt", operations=[
            {"op": "replace", "anchor": pos2, "lines": ["B2"]},
        ])
        assert r4.success, r4.error
        assert "B2" in (tmp_path / "deg_mtime.txt").read_text(encoding="utf-8")


class TestLegacyParamCompatibility:
    """Block-1：旧参数兼容兜底（edits / pos 仍可用，不破坏 T3 既有调用）"""

    def test_legacy_edits_pos(self, tmp_path):
        write_file(tmp_path, "a\nb\nc\n")
        ctx = make_ctx(tmp_path)
        r1 = read_tool._read_impl(ctx, path="t.txt")
        pos = read_pos(r1, 2)
        r2 = edit_tool._edit_impl(ctx, path="t.txt", edits=[
            {"op": "replace", "pos": pos, "lines": ["B2"]},
        ])
        assert r2.success, r2.error
        assert (tmp_path / "t.txt").read_text(encoding="utf-8") == "a\nB2\nc\n"

    def test_operations_takes_precedence(self, tmp_path):
        """同时传 operations 与 edits 时以 operations 为准"""
        write_file(tmp_path, "a\nb\nc\n")
        ctx = make_ctx(tmp_path)
        r1 = read_tool._read_impl(ctx, path="t.txt")
        pos = read_pos(r1, 1)
        r2 = edit_tool._edit_impl(ctx, path="t.txt",
                                  operations=[{"op": "replace", "anchor": pos, "lines": ["A1"]}],
                                  edits=[{"op": "replace", "anchor": pos, "lines": ["IGNORED"]}])
        assert r2.success, r2.error
        assert (tmp_path / "t.txt").read_text(encoding="utf-8") == "A1\nb\nc\n"

    def test_snapshot_accepts_anchor_and_pos(self):
        lines = ["a", "b", "c"]
        hs = engine.hash_all(lines)
        # anchor 主字段
        new, meta = snapshot.apply_edits(lines, [
            {"op": "replace", "anchor": f"2#{hs[1]}", "lines": ["B"]},
        ])
        assert not meta["errors"] and new == ["a", "B", "c"]
        # pos 兼容兜底
        new, meta = snapshot.apply_edits(lines, [
            {"op": "replace", "pos": f"3#{hs[2]}", "lines": ["C"]},
        ])
        assert not meta["errors"] and new == ["a", "b", "C"]
        # 缺 anchor 且缺 pos → E_INVALID_PATCH
        new, meta = snapshot.apply_edits(lines, [
            {"op": "replace", "lines": ["X"]},
        ])
        assert meta["errors"] and snapshot.E_INVALID_PATCH in meta["errors"][0]
