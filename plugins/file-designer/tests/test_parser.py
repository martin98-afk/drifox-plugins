# -*- coding: utf-8 -*-
"""docx_parser 纯函数单测（无 Qt 依赖，系统 python + python-docx 直接跑）。

Run: python -m pytest plugins/file-designer/tests/test_parser.py -v
"""
import importlib.util
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1]


def _load_module(mod_name, filename):
    """按文件路径加载插件 ui 模块（避免与其它插件的顶层 ui 包名冲突）"""
    spec = importlib.util.spec_from_file_location(mod_name, PLUGIN / "ui" / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


_docx_parser = _load_module("file_designer_docx_parser", "docx_parser.py")
parse_document = _docx_parser.parse_document

DEMO_OMML = (
    PLUGIN.parent / "omml-docx" / "skills" / "omml-docx" / "scripts" / "demo_omml.docx"
)


@pytest.fixture(scope="session")
def sample_docx(tmp_path_factory):
    """基本样本：标题/正文/加粗斜体/列表。"""
    from docx import Document

    doc = Document()
    doc.add_heading("测试文档", level=1)
    doc.add_heading("第一章", level=2)
    doc.add_paragraph("普通段落内容。")
    p = doc.add_paragraph()
    r1 = p.add_run("加粗")
    r1.bold = True
    r2 = p.add_run("普通")
    r2.italic = True
    doc.add_paragraph("列表项一", style="List Bullet")
    doc.add_paragraph("列表项二", style="List Bullet")
    path = tmp_path_factory.mktemp("s") / "sample.docx"
    doc.save(str(path))
    return path


def _save(doc, tmp_path, name="t.docx"):
    path = tmp_path / name
    doc.save(str(path))
    return path


def test_blocks_have_sequential_anchors(sample_docx):
    blocks = parse_document(str(sample_docx))
    assert [b["index"] for b in blocks] == list(range(len(blocks)))
    assert all(b["anchor"] == str(b["index"]) for b in blocks)


def test_heading_levels(sample_docx):
    blocks = parse_document(str(sample_docx))
    heads = [b for b in blocks if b["kind"] == "heading"]
    assert heads[0]["text"] == "测试文档" and heads[0]["level"] == 1
    assert heads[1]["text"] == "第一章" and heads[1]["level"] == 2


def test_runs_styles(sample_docx):
    blocks = parse_document(str(sample_docx))
    p = next(b for b in blocks if "加粗" in b["text"])
    bold = next(r for r in p["runs"] if r.get("text") == "加粗")
    assert bold["bold"] is True
    italic = next(r for r in p["runs"] if r.get("text") == "普通")
    assert italic["italic"] is True and italic["bold"] is False


def test_list_flag(sample_docx):
    blocks = parse_document(str(sample_docx))
    lists = [b for b in blocks if b.get("is_list") or b.get("list_label")]
    assert len(lists) == 2
    assert lists[0]["text"] == "列表项一"


def test_table_gridspan_vmerge(tmp_path):
    from docx import Document

    doc = Document()
    tbl = doc.add_table(rows=3, cols=3)
    tbl.cell(0, 0).merge(tbl.cell(0, 1))  # 首行横跨 2 列 → colspan=2
    tbl.cell(1, 0).merge(tbl.cell(2, 0))  # 首列纵跨 2 行 → rowspan=2
    tbl.cell(0, 0).text = "跨列"
    tbl.cell(0, 2).text = "右上"
    tbl.cell(1, 1).text = "中"
    path = _save(doc, tmp_path)
    blocks = parse_document(str(path))
    t = next(b for b in blocks if b["kind"] == "table")
    row0 = t["rows"][0]
    assert row0[0]["colspan"] == 2
    assert row0[0]["text"] == "跨列"
    assert row0[0]["anchor"] == f"{t['index']}:r0c0"
    assert row0[1]["text"] == "右上"
    # 纵向合并：r1c0 rowspan=2，r2 首格被吞并
    r1c0 = t["rows"][1][0]
    assert r1c0["rowspan"] == 2 and r1c0["anchor"] == f"{t['index']}:r1c0"
    assert all(c["col"] != 0 for c in t["rows"][2])


def test_cell_multi_paragraph_runs(tmp_path):
    """多段单元格必须保留全部段落 runs（回归：曾只回传首段，简历正文整段丢失）。"""
    from docx import Document

    doc = Document()
    tbl = doc.add_table(rows=1, cols=2)
    cell = tbl.cell(0, 0)
    cell.text = "第一段"
    p2 = cell.add_paragraph()
    r2 = p2.add_run("第二段")
    r2.bold = True
    p3 = cell.add_paragraph("第三段")
    tbl.cell(0, 1).text = "旁"
    path = _save(doc, tmp_path)
    blocks = parse_document(str(path))
    t = next(b for b in blocks if b["kind"] == "table")
    c = t["rows"][0][0]
    texts = [r["text"] for r in c["runs"] if "text" in r]
    assert "第一段" in texts and "第二段" in texts and "第三段" in texts
    assert "\n" in texts  # 段落分隔标记，渲染层转 <br>
    bold = next(r for r in c["runs"] if r.get("text") == "第二段")
    assert bold["bold"] is True
    assert c["text"] == "第一段\n第二段\n第三段"
    # 逐段落结构：供渲染层出块级 <p> 与分页行内拆分
    assert len(c["para_runs"]) == 3
    assert any(r.get("text") == "第二段" and r.get("bold") for r in c["para_runs"][1])

def test_omml_math_extracted(tmp_path):
    """用 omml-docx 的构造器造一个含下标公式的文档。"""
    omml_scripts = PLUGIN.parent / "omml-docx" / "skills" / "omml-docx" / "scripts"
    sys.path.insert(0, str(omml_scripts))
    try:
        from omml_utils import build_docx, mixed_para, sub_math

        body = mixed_para([("text", "状态 "), ("math", sub_math("x", "t")), ("text", "。")])
        out = tmp_path / "m.docx"
        build_docx(body, str(out))
    finally:
        sys.path.remove(str(omml_scripts))
    blocks = parse_document(str(out))
    p = next(b for b in blocks if "状态" in b["text"])
    assert any("math" in r for r in p["runs"])
    assert "xt" in p["text"] or "x" in p["text"]


@pytest.mark.skipif(not DEMO_OMML.exists(), reason="demo_omml.docx 不存在")
def test_demo_omml_parses():
    blocks = parse_document(str(DEMO_OMML))
    maths = [b for b in blocks if any("math" in r for r in b["runs"])]
    assert len(maths) >= 3
