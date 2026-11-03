# -*- coding: utf-8 -*-
"""pick_format 回填格式化单测（无 Qt 依赖）。

Run: python -m pytest plugins/docx-designer/tests/test_pick_format.py -v
"""
import importlib.util
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]


def _load_module(mod_name, filename):
    spec = importlib.util.spec_from_file_location(mod_name, PLUGIN / "ui" / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


pf = _load_module("docx_designer_pick_format", "pick_format.py")
format_pick = pf.format_pick
format_table_text = pf.format_table_text


def _table_block():
    return {
        "kind": "table", "index": 52, "anchor": "52",
        "rows": [
            [
                {"text": "章主题", "anchor": "52:r0c0", "col": 0, "colspan": 1, "rowspan": 1},
                {"text": "看完能回答什么", "anchor": "52:r0c1", "col": 1, "colspan": 1, "rowspan": 1},
            ],
            [
                {"text": "1 通用控制问题的定义", "anchor": "52:r1c0", "col": 0, "colspan": 1, "rowspan": 1},
                {"text": "MV×nCV 在工业里\n到底是个什么问题", "anchor": "52:r1c1", "col": 1, "colspan": 1, "rowspan": 1},
            ],
        ],
    }


def test_cell_pick_has_cell_row_and_full_table():
    text = format_pick(1, r"C:\docs\a.docx", "52:r1c1", _table_block(), "MV", None)
    assert r"C:\docs\a.docx" in text          # 绝对路径
    assert "[表格 #52 单元格 r1c1]" in text
    assert '"MV×nCV 在工业里\n到底是个什么问题"' in text   # 格文本（保留原始换行）
    assert "所在行: 1 通用控制问题的定义 | MV" in text
    assert "表格全文:" in text and "章主题 | 看完能回答什么" in text


def test_table_pick_full_text():
    text = format_pick(2, r"C:\docs\a.docx", "52", _table_block(), "章主题…", None)
    assert "[表格 #52]" in text
    assert "1 通用控制问题的定义 | MV" in text


def test_paragraph_full_text_not_truncated_under_cap():
    b = {"kind": "paragraph", "anchor": "3", "style": "", "text": "段落" * 100, "runs": []}
    text = format_pick(3, r"C:\docs\a.docx", "3", b, "", None)
    assert "段落" * 100 in text


def test_paragraph_truncated_over_cap():
    b = {"kind": "paragraph", "anchor": "4", "style": "Heading 1", "text": "长" * 2000, "runs": []}
    text = format_pick(4, r"C:\docs\a.docx", "4", b, "", None)
    assert "…(截断)" in text


def test_image_block():
    b = {"kind": "image", "anchor": "7", "text": "", "runs": []}
    text = format_pick(5, r"C:\docs\a.docx", "7", b, "", r"C:\picks\pick.png")
    assert "[图片 #7]" in text and "截图：C:\\picks\\pick.png" in text


def test_guide_on_first_pick():
    b = {"kind": "paragraph", "anchor": "0", "style": "", "text": "x", "runs": []}
    with_guide = format_pick(1, r"C:\a.docx", "0", b, "", None, include_guide=True)
    without = format_pick(2, r"C:\a.docx", "0", b, "", None)
    assert "锚点规则" in with_guide
    assert "锚点规则" not in without


def test_table_text_truncation():
    rows = [[{"text": "x" * 100, "anchor": "0:r0c0", "col": 0}] for _ in range(50)]
    assert len(format_table_text(rows)) <= pf._TABLE_CAP + 10


def test_format_annotations_layout():
    anns = [
        {"anchor": "12", "comment": "逻辑不通", "seq": 1, "snippet": "为什么要先做 X"},
        {"anchor": "15:r1c0", "comment": "数值来源？", "seq": 2, "snippet": "0.82"},
    ]
    text = pf.format_annotations(r"C:\d\a.docx", anns)
    assert "共 2 条" in text and r"C:\d\a.docx" in text
    assert "①[元素 #12]" in text and "②[表格 #15 单元格 r1c0]" in text
    assert "↳ 注释：逻辑不通" in text
    assert "锚点规则" in text
