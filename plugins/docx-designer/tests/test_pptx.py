# -*- coding: utf-8 -*-
"""pptx 解析/渲染单测（无 Qt 依赖，系统 python + python-pptx 直接跑）。

Run: python -m pytest plugins/docx-designer/tests/test_pptx.py -v
"""
import importlib
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1]


def _load_ui_module(name):
    if str(PLUGIN) not in sys.path:
        sys.path.insert(0, str(PLUGIN))
    for key in [k for k in sys.modules if k == "ui" or k.startswith("ui.")]:
        del sys.modules[key]
    return importlib.import_module(f"ui.{name}")


@pytest.fixture(scope="module")
def deck(tmp_path_factory):
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    path = tmp_path_factory.mktemp("pptx") / "deck.pptx"
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    s1 = prs.slides.add_slide(prs.slide_layouts[0])
    s1.shapes.title.text = "封面标题"
    s1.placeholders[1].text = "副标题"
    s2 = prs.slides.add_slide(prs.slide_layouts[5])
    s2.shapes.title.text = "第二页"
    box = s2.shapes.add_textbox(Inches(1), Inches(2), Inches(4), Inches(1.5))
    p = box.text_frame.paragraphs[0]
    p.text = "正文段落"
    p.runs[0].font.size = Pt(20)
    p.runs[0].font.bold = True
    p.runs[0].font.color.rgb = RGBColor(0x11, 0x22, 0x33)
    tbl = s2.shapes.add_table(2, 2, Inches(6), Inches(2), Inches(4), Inches(1)).table
    tbl.cell(0, 0).text = "A"
    tbl.cell(0, 1).text = "B"
    tbl.cell(1, 0).text = "C"
    tbl.cell(1, 1).text = "D"
    prs.save(str(path))
    return path


def test_parse_canvas_and_slides(deck):
    parser = _load_ui_module("pptx_parser")
    model = parser.parse_presentation(str(deck))
    assert model["w_pt"] == pytest.approx(959.98, abs=0.5)
    assert model["h_pt"] == pytest.approx(540.0, abs=0.5)
    assert len(model["slides"]) == 2
    assert model["slides"][0]["bg"].startswith("#")


def test_placeholder_text_and_font(deck):
    parser = _load_ui_module("pptx_parser")
    model = parser.parse_presentation(str(deck))
    title = model["slides"][0]["shapes"][0]
    assert title["kind"] == "text"
    assert title["paras"][0]["runs"][0]["text"] == "封面标题"
    # 占位符字号回退：中心标题 44pt
    assert title["paras"][0]["runs"][0]["size_pt"] == pytest.approx(44.0)


def test_run_props_and_table(deck):
    parser = _load_ui_module("pptx_parser")
    model = parser.parse_presentation(str(deck))
    shapes = model["slides"][1]["shapes"]
    box = next(s for s in shapes if s["kind"] == "text" and s["top"] > 100)
    run = box["paras"][0]["runs"][0]
    assert run["text"] == "正文段落"
    assert run["size_pt"] == pytest.approx(20.0)
    assert run["bold"] is True
    assert run["color"].lower() == "#112233"
    table = next(s for s in shapes if s["kind"] == "table")
    assert table["rows"][0][0]["text"] == "A"
    assert table["rows"][1][1]["text"] == "D"
    assert len(table["col_widths"]) == 2


def test_render_html(deck):
    parser = _load_ui_module("pptx_parser")
    renderer = _load_ui_module("pptx_renderer")
    model = parser.parse_presentation(str(deck))
    html = renderer.render_pptx_html(model, restored=[{"anchor": "0:0", "comment": "改标题", "seq": 1}])
    assert 'data-anchor="0:0"' in html
    assert "封面标题" in html
    assert "<table>" in html
    assert "window.__restored" in html
    assert "改标题" in html
