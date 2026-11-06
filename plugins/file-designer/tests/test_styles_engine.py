# -*- coding: utf-8 -*-
"""样式引擎保真渲染单测（样式链/编号/段落属性/表格列宽）。

Run: python -m pytest plugins/file-designer/tests/test_styles_engine.py -v
"""
import importlib.util
import sys
from pathlib import Path

from lxml import etree

PLUGIN = Path(__file__).resolve().parents[1]
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _load_module(mod_name, filename):
    spec = importlib.util.spec_from_file_location(mod_name, PLUGIN / "ui" / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


dp = _load_module("file_designer_docx_parser2", "docx_parser.py")
hr = _load_module("file_designer_html_renderer2", "html_renderer.py")


def _w(tag, **attrs):
    el = etree.SubElement(etree.Element(f"{{{W}}}root"), f"{{{W}}}{tag}")
    for k, v in attrs.items():
        el.set(f"{{{W}}}{k}", v)
    return el


def test_para_props_extraction():
    ppr = etree.Element(f"{{{W}}}pPr")
    jc = etree.SubElement(ppr, f"{{{W}}}jc")
    jc.set(f"{{{W}}}val", "center")
    ind = etree.SubElement(ppr, f"{{{W}}}ind")
    ind.set(f"{{{W}}}firstLineChars", "200")
    ind.set(f"{{{W}}}left", "420")
    sp = etree.SubElement(ppr, f"{{{W}}}spacing")
    sp.set(f"{{{W}}}before", "120")
    sp.set(f"{{{W}}}line", "360")
    props = dp._para_props(ppr)
    assert props["align"] == "center"
    assert props["first_line_chars"] == 2.0
    assert props["left_pt"] == 21.0
    assert props["before_pt"] == 6.0
    assert props["line"] == 1.5


def test_run_props_extraction():
    rpr = etree.Element(f"{{{W}}}rPr")
    sz = etree.SubElement(rpr, f"{{{W}}}sz")
    sz.set(f"{{{W}}}val", "32")
    color = etree.SubElement(rpr, f"{{{W}}}color")
    color.set(f"{{{W}}}val", "FF0000")
    props = dp._run_props(rpr)
    assert props["size_pt"] == 16.0 and props["color"] == "#FF0000"


def test_style_chain_based_on_inheritance():
    styles_map = {
        "Base": {"name": "Base", "basedOn": None,
                 "p": {"align": "left"}, "r": {"size_pt": 10.5}},
        "Child": {"name": "Child", "basedOn": "Base",
                  "p": {}, "r": {"bold": True}},
    }
    p, r = dp._resolve_style_chain("Child", styles_map)
    assert r["size_pt"] == 10.5 and r["bold"] is True
    assert p["align"] == "left"


def test_numbering_multilevel_label():
    counter = dp._NumberingCounter()
    numbering = {
        "nums": {"1": "0"},
        "abstracts": {"0": {
            0: {"fmt": "decimal", "text": "%1.", "first_pt": None, "left_pt": None},
            1: {"fmt": "decimal", "text": "%1.%2", "first_pt": None, "left_pt": None},
        }},
    }
    assert counter.next(numbering, "1", 0)[0] == "1."
    assert counter.next(numbering, "1", 1)[0] == "1.1"
    assert counter.next(numbering, "1", 1)[0] == "1.2"
    assert counter.next(numbering, "1", 0)[0] == "2."
    assert counter.next(numbering, "1", 1)[0] == "2.1"  # 二级计数已重置


def test_numbering_bullet_symbol_mapped():
    counter = dp._NumberingCounter()
    numbering = {
        "nums": {"5": "7"},
        "abstracts": {"7": {0: {"fmt": "bullet", "text": "\uF0B7", "first_pt": None, "left_pt": None}}},
    }
    assert counter.next(numbering, "5", 0)[0] == "\u2022"


def test_parse_document_injects_fmt_and_labels(tmp_path):
    """真实文档：标题块应有 fmt，列表应有编号 label。"""
    from docx import Document

    doc = Document()
    doc.add_heading("测试文档", level=1)
    doc.add_paragraph("列表项一", style="List Bullet")
    path = tmp_path / "s.docx"
    doc.save(str(path))
    blocks = dp.parse_document(str(path))
    head = next(b for b in blocks if b["kind"] == "heading")
    assert "fmt" in head and isinstance(head["fmt"], dict)
    lists = [b for b in blocks if b.get("list_label")]
    assert lists and lists[0]["list_label"]


def test_renderer_fmt_inline_and_colgroup():
    b = {
        "kind": "paragraph", "index": 0, "anchor": "0", "style": "", "level": 0,
        "text": "居中", "runs": [{"text": "居中", "bold": False, "italic": False,
        "underline": False}], "is_list": False,
        "fmt": {"align": "center", "size_pt": 16.0, "color": "#FF0000", "font": "黑体"},
    }
    html = hr.render_html([b])
    assert "text-align:center" in html
    assert "font-size:1.52em" in html   # 16/10.5
    assert "color:#FF0000" in html
    assert "font-family:" in html and "黑体" in html

    t = {
        "kind": "table", "index": 1, "anchor": "1", "style": "", "level": 0,
        "text": "", "runs": [], "is_list": False,
        "col_widths": [3000, 1000],
        "rows": [[{"text": "宽", "anchor": "1:r0c0", "col": 0, "colspan": 1, "rowspan": 1},
                  {"text": "窄", "anchor": "1:r0c1", "col": 1, "colspan": 1, "rowspan": 1}]],
    }
    html = hr.render_html([t])
    assert "<colgroup>" in html and "width:75.0%" in html and "width:25.0%" in html


def test_render_html_doc_font_inferred():
    b = {"kind": "paragraph", "index": 0, "anchor": "0", "style": "", "level": 0,
         "text": "x", "runs": [], "is_list": False,
         "fmt": {"font": "仿宋"}}
    html = hr.render_html([b], doc_font=None)
    assert "font-family:" in html and "仿宋" in html
