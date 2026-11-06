# -*- coding: utf-8 -*-
"""pick_format 多格式回填单测（无 Qt 依赖，覆盖 6 类 mode）。

Run: python -m pytest plugins/file-designer/tests/test_pick_format_formats.py -q --noconftest
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

pf = _load_module("file_designer_pick_format_formats", "pick_format.py")

SHOT = r"C:\picks\pick.png"

def test_docx_mode_paragraph_with_shot():
    b = {"kind": "paragraph", "anchor": "3", "style": "Heading 1", "text": "引言", "runs": []}
    t = pf.format_pick(1, r"C:\d\a.docx", "3", b, "", SHOT, mode="docx")
    assert t.startswith("📎 docx 拾取 #1 [C:\\d\\a.docx]")
    assert "[paragraph | Heading 1]" in t
    assert '"引言"' in t
    assert f"截图：{SHOT}" in t

def test_pptx_mode_element_desc():
    b = {"kind": "text", "anchor": "2:5", "text": "标题文本"}
    t = pf.format_pick(1, r"C:\d\deck.pptx", "2:5", b, "", None, mode="pptx")
    assert t.startswith("📎 pptx 拾取 #1")
    assert "[幻灯片 3 元素 6]" in t          # 0 起 → 展示 1 起
    assert '"标题文本"' in t

def test_xmind_node_pick():
    b = {
        "mode": "xmind", "kind": "xmind_node",
        "path": ["产品规划", "Q3", "登录改版"],
        "siblings": ["支付重构", "搜索优化"],
        "text": "登录改版", "note": "需兼容 SSO",
    }
    t = pf.format_pick(1, r"C:\d\map.xmind", "s0/n/0.2.1", b, "", SHOT, mode="xmind")
    assert t.startswith("📎 xmind 拾取 #1 [C:\\d\\map.xmind]")
    assert "[节点 s0/n/0.2.1]" in t
    assert "层级: 产品规划 → Q3 → 登录改版" in t
    assert "同级: 支付重构 | 搜索优化" in t
    assert '"登录改版"' in t and "备注: 需兼容 SSO" in t
    assert f"截图：{SHOT}" in t

def test_xlsx_cell_pick():
    b = {
        "mode": "xlsx", "kind": "sheet_cell",
        "sheet": "2026Q3", "header": "营收", "text": "1234",
        "row_text": "Q3 | 1234 | 同比+5%",
    }
    t = pf.format_pick(2, r"C:\d\b.xlsx", "s1!B3", b, "", None, mode="xlsx")
    assert t.startswith("📎 excel 拾取 #2")
    assert "[单元格 s1!B3]" in t
    assert "工作表: 2026Q3" in t
    assert "表头: 营收" in t
    assert '"1234"' in t
    assert "所在行: Q3 | 1234 | 同比+5%" in t

def test_xlsm_shares_xlsx_mode():
    b = {"mode": "xlsx", "kind": "sheet_cell", "text": "宏表"}
    t = pf.format_pick(1, r"C:\d\m.xlsm", "s0!A1", b, "", None)
    assert t.startswith("📎 excel 拾取 #1")   # block.mode 驱动，不靠 mode 参数
    assert "[单元格 s0!A1]" in t

def test_csv_cell_pick():
    b = {
        "mode": "csv", "kind": "sheet_cell",
        "header": "城市", "text": "上海", "row_text": "上海 | 晴 | 26",
    }
    t = pf.format_pick(1, r"C:\d\w.csv", "r2c0", b, "", SHOT, mode="csv")
    assert t.startswith("📎 csv 拾取 #1 [C:\\d\\w.csv]")
    assert "[单元格 r2c0]" in t
    assert "表头: 城市" in t and '"上海"' in t
    assert "所在行: 上海 | 晴 | 26" in t
    assert f"截图：{SHOT}" in t

def test_csv_table_pick():
    b = {
        "mode": "csv", "kind": "sheet_table",
        "rows": [
            [{"text": "城市", "anchor": "r0c0"}, {"text": "天气", "anchor": "r0c1"}],
            [{"text": "上海", "anchor": "r1c0"}, {"text": "晴", "anchor": "r1c1"}],
        ],
    }
    t = pf.format_pick(1, r"C:\d\w.csv", "table", b, "", None, mode="csv")
    assert "[整表]" in t
    assert "表格全文:" in t and "城市 | 天气" in t and "上海 | 晴" in t

def test_mermaid_line_pick():
    b = {
        "mode": "mermaid", "kind": "mermaid_line",
        "diagram_type": "flowchart TD", "text": "A --> B",
        "context": "flowchart TD\n  A[开始] --> B[结束]",
    }
    t = pf.format_pick(1, r"C:\d\flow.mmd", "L3", b, "", SHOT, mode="mermaid")
    assert t.startswith("📎 mermaid 拾取 #1 [C:\\d\\flow.mmd]")
    assert "[源码 L3]" in t
    assert "图类型: flowchart TD" in t
    assert '"A --> B"' in t
    assert "上下文:\nflowchart TD" in t
    assert f"截图：{SHOT}" in t

def test_generic_falls_back_to_preview_when_block_empty():
    b = {"mode": "mermaid", "kind": "mermaid_line"}
    t = pf.format_pick(1, r"C:\d\flow.mmd", "L1", b, "graph TD", None, mode="mermaid")
    assert '"graph TD"' in t

def test_guide_rules_per_mode():
    cases = [
        ("xmind", "s0/n/0", "s工作表序号/n/节点路径"),
        ("xlsx", "s1!B3", "列字母行号"),
        ("csv", "r1c0", "均 0 起,第 0 行是表头"),
        ("mermaid", "L1", "1 起"),
        ("docx", "3", "body 第 N 个块"),
        ("pptx", "0:1", "0 起"),
    ]
    for mode, anchor, marker in cases:
        t = pf.format_pick(1, r"C:\d\f.bin", anchor, None, "", None,
                           include_guide=True, mode=mode)
        assert "锚点规则" in t and marker in t, mode
        assert "可用 open_file 工具重新打开该文件定位" in t

def test_annotations_all_modes():
    labels = {
        "docx": "docx", "pptx": "pptx", "xmind": "xmind",
        "xlsx": "excel", "csv": "csv", "mermaid": "mermaid",
    }
    for mode, label in labels.items():
        anns = [{"anchor": "x", "comment": "改这里", "seq": 1, "snippet": "片段"}]
        t = pf.format_annotations(r"C:\d\f.bin", anns, mode=mode)
        assert t.startswith(f"📝 {label} 标注 共 1 条"), mode
        assert "↳ 注释：改这里" in t and "锚点规则" in t

def test_annotations_desc_per_mode():
    cases = [
        ("xmind", "s0/n/0", "[节点 s0/n/0]"),
        ("xlsx", "s0!A1", "[单元格 s0!A1]"),
        ("csv", "table", "[整表]"),
        ("mermaid", "L2", "[源码 L2]"),
    ]
    for mode, anchor, marker in cases:
        anns = [{"anchor": anchor, "comment": "c", "seq": 1, "snippet": "s", "shot": SHOT}]
        t = pf.format_annotations(r"C:\d\f.bin", anns, mode=mode)
        assert marker in t, mode
        assert f"  截图：{SHOT}" in t

def test_normalize_annotations_legacy():
    old = [{"anchor": "52", "comment": "c", "seq": 1, "snippet": "s"}]
    out = pf.normalize_annotations(old)
    assert out[0]["anchors"] == ["52"]
    assert "anchor" not in out[0]
    assert old[0].get("anchor") == "52"  # 不修改输入

def test_normalize_annotations_keeps_groups():
    g = [{"anchors": ["a", "b"], "comment": "c", "seq": 2, "snippet": "s"}]
    assert pf.normalize_annotations(g)[0]["anchors"] == ["a", "b"]

def test_normalize_annotations_empty_and_bad():
    assert pf.normalize_annotations([]) == []
    assert pf.normalize_annotations(None) == []
    assert pf.normalize_annotations([{"comment": "no-anchor"}])[0]["anchors"] == ["?"]

def test_format_annotations_group_entries():
    anns = [
        {"anchors": ["52:r1c1", "52:r2c1"], "comment": "整组说明", "seq": 1, "snippet": "首元素"},
        {"anchors": ["3", "4", "5", "6", "7", "8"], "comment": "多条", "seq": 2, "snippet": "x"},
    ]
    t = pf.format_annotations(r"C:\d\a.docx", anns, mode="docx")
    assert "[表格 #52 单元格 r1c1]、[表格 #52 单元格 r2c1]" in t
    assert "等 6 处" in t
    assert "↳ 注释：整组说明" in t

def test_format_annotations_single_compat():
    """单锚点条目输出与旧版一致（回归）。"""
    anns = [{"anchors": ["52"], "comment": "改标题", "seq": 1, "snippet": "章主题"}]
    t = pf.format_annotations(r"C:\d\a.docx", anns, mode="docx")
    assert "[元素 #52] \"章主题\"" in t

def test_format_batch_pick():
    items = [
        {"anchor": "0", "preview": "第一段"},
        {"anchor": "1", "preview": "第二段"},
        {"anchor": "2", "preview": "第三段"},
    ]
    blocks = {"1": {"kind": "paragraph", "text": "第二段全文", "style": "Normal"}}
    t = pf.format_batch_pick(3, r"C:\d\a.docx", items, blocks,
                             SHOT, mode="docx", first_guide=False)
    assert t.count("拾取 #") == 3
    assert "#3" in t and "#4" in t and "#5" in t
    assert t.count("截图：") == 1  # 截图仅首条携带
    assert "第二段全文" in t  # block 上下文按锚点携带
    assert "锚点规则" not in t  # first_guide=False 不附指引

def test_format_batch_pick_first_guide():
    items = [{"anchor": "0", "preview": "x"}]
    t = pf.format_batch_pick(0, r"C:\d\a.docx", items, {}, None,
                             mode="docx", first_guide=True)
    assert "锚点规则" in t
