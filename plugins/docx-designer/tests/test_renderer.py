# -*- coding: utf-8 -*-
"""html_renderer 纯函数单测。

Run: python -m pytest plugins/docx-designer/tests/test_renderer.py -v
"""
import importlib.util
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]


def _load_module(mod_name, filename):
    """按文件路径加载插件 ui 模块（避免与其它插件的顶层 ui 包名冲突）"""
    spec = importlib.util.spec_from_file_location(mod_name, PLUGIN / "ui" / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


render_html = _load_module("docx_designer_html_renderer", "html_renderer.py").render_html


def _para(idx, text, **kw):
    b = {
        "kind": "paragraph", "index": idx, "anchor": str(idx),
        "style": "", "level": 0, "text": text, "runs": kw.get("runs") or [
            {"text": text, "bold": False, "italic": False, "underline": False}
        ],
        "is_list": kw.get("is_list", False),
    }
    return b


def test_html_contains_anchors():
    html = render_html([_para(0, "第一段"), _para(1, "第二段")])
    assert 'data-anchor="0"' in html and 'data-anchor="1"' in html
    assert "第一段" in html


def test_heading_tags():
    h = {
        "kind": "heading", "index": 0, "anchor": "0", "style": "Heading 1",
        "level": 1, "text": "大标题", "runs": [{"text": "大标题", "bold": True,
        "italic": False, "underline": False}], "is_list": False,
    }
    html = render_html([h])
    assert "<h1" in html and "</h1>" in html


def test_run_style_tags():
    p = _para(0, "x", runs=[
        {"text": "粗", "bold": True, "italic": False, "underline": False},
        {"text": "斜", "bold": False, "italic": True, "underline": False},
        {"text": "下", "bold": False, "italic": False, "underline": True},
    ])
    html = render_html([p])
    assert "<strong>粗</strong>" in html
    assert "<em>斜</em>" in html
    assert "<u>下</u>" in html


def test_table_col_row_span():
    t = {
        "kind": "table", "index": 5, "anchor": "5", "style": "", "level": 0,
        "text": "", "runs": [], "is_list": False,
        "rows": [[
            {"text": "跨", "runs": [], "colspan": 2, "rowspan": 1,
             "col": 0, "anchor": "5:r0c0"},
            {"text": "右", "runs": [], "colspan": 1, "rowspan": 1,
             "col": 2, "anchor": "5:r0c2"},
        ]],
    }
    html = render_html([t])
    assert 'colspan="2"' in html
    assert 'data-anchor="5:r0c2"' in html


def test_math_html_frac_sub_sup():
    from lxml import etree

    omml_to_html = _load_module(
        "docx_designer_html_renderer", "html_renderer.py"
    ).omml_to_html

    M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
    frac_xml = (
        f'<m:oMath xmlns:m="{M}"><m:f><m:num><m:r><m:t>a</m:t></m:r></m:num>'
        f'<m:den><m:r><m:t>b</m:t></m:r></m:den></m:f>'
        f'<m:sSub><m:e><m:r><m:t>x</m:t></m:r></m:e>'
        f'<m:sub><m:r><m:t>i</m:t></m:r></m:sub></m:sSub></m:oMath>'
    )
    html = omml_to_html(etree.fromstring(frac_xml.encode()))
    assert 'class="frac"' in html
    assert "<sub>" in html and ">i<" in html


def test_image_block_renders_img():
    p = _para(3, "", runs=[{"image": "data:image/png;base64,AAAA"}])
    p["kind"] = "image"
    p["image"] = "data:image/png;base64,AAAA"
    html = render_html([p])
    assert "<figure" in html and 'src="data:image/png;base64,AAAA"' in html


def test_pick_js_and_channel_script():
    html = render_html([_para(0, "x")])
    assert "qwebchannel.js" in html
    assert "docxbridge" in html
    assert "classList.contains('pick')" in html
