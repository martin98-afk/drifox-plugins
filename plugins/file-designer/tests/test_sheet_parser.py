# -*- coding: utf-8 -*-
"""Excel / CSV 解析与渲染单测（无 Qt 依赖）。

Run: python -m pytest plugins/file-designer/tests/test_sheet_parser.py -q --noconftest
"""
import importlib
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1]

@pytest.fixture(scope="module", autouse=True)
def _ui_package():
    if str(PLUGIN) not in sys.path:
        sys.path.insert(0, str(PLUGIN))
    for key in [k for k in sys.modules if k == "ui" or k.startswith("ui.")]:
        del sys.modules[key]

def _mod(name):
    return importlib.import_module(f"ui.{name}")

def _xlsx(tmp_path):
    from openpyxl import Workbook
    p = tmp_path / "book.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "2026Q3"
    ws.append(["季度", "营收", "备注"])
    ws.append(["Q3", 1234, "同比+5%"])
    ws.append(["Q4", 2345, "预算"])
    ws.column_dimensions["B"].width = 22
    ws.merge_cells("C2:C3")
    ws2 = wb.create_sheet("附录")
    ws2.append(["键", "值"])
    ws2.append(["来源", "财务系统"])
    wb.save(str(p))
    return p

def test_xlsx_cells_and_anchors(tmp_path):
    sp = _mod("sheet_parser")
    m = sp.parse_xlsx(str(_xlsx(tmp_path)))
    assert m["mode"] == "xlsx" and not m["truncated"]
    assert len(m["sheets"]) == 2
    b = m["lookup"]("s0!B2")
    assert b["mode"] == "xlsx" and b["kind"] == "sheet_cell"
    assert b["text"] == "1234" and b["header"] == "营收"
    assert b["sheet"] == "2026Q3"
    assert "Q3 | 1234 | 同比+5%" == b["row_text"]
    assert m["lookup"]("s1!A2")["text"] == "来源"
    assert m["lookup"]("s0!Z9") is None

def test_xlsx_merges_and_col_widths(tmp_path):
    sp = _mod("sheet_parser")
    m = sp.parse_xlsx(str(_xlsx(tmp_path)))
    sh = m["sheets"][0]
    assert any(x == {"r": 1, "c": 2, "rs": 2, "cs": 1} for x in sh["merges"])
    assert sh["rows"][2][2]["covered"] is True
    assert sh["col_widths"][1] > sh["col_widths"][0]   # B 列设了更宽

def test_xlsx_table_anchor(tmp_path):
    sp = _mod("sheet_parser")
    m = sp.parse_xlsx(str(_xlsx(tmp_path)))
    b = m["lookup"]("s0!table")
    assert b["kind"] == "sheet_table" and len(b["rows"]) == 3

def test_csv_encoding_chain_and_delimiter(tmp_path):
    sp = _mod("sheet_parser")
    p = tmp_path / "gb.csv"
    p.write_bytes("城市;天气;温度\n上海;晴;26\n北京;雨;18\n".encode("gb18030"))
    m = sp.parse_csv(str(p))
    assert m["mode"] == "csv" and not m["truncated"]
    assert m["sheets"][0]["rows"][0][0]["text"] == "城市"
    assert m["sheets"][0]["rows"][1][2]["text"] == "26"

def test_csv_utf8_bom(tmp_path):
    sp = _mod("sheet_parser")
    p = tmp_path / "bom.csv"
    p.write_bytes("城市,天气\n上海,晴\n".encode("utf-8-sig"))
    m = sp.parse_csv(str(p))
    assert m["sheets"][0]["rows"][0][0]["text"] == "城市"

def test_csv_lookup_cell_and_table(tmp_path):
    sp = _mod("sheet_parser")
    p = tmp_path / "w.csv"
    p.write_text("城市,天气,温度\n上海,晴,26\n北京,雨,18\n", encoding="utf-8")
    m = sp.parse_csv(str(p))
    b = m["lookup"]("r2c0")
    assert b["kind"] == "sheet_cell" and b["text"] == "北京"
    assert b["header"] == "城市" and "北京 | 雨 | 18" == b["row_text"]
    t = m["lookup"]("table")
    assert t["kind"] == "sheet_table" and len(t["rows"]) == 3
    assert m["lookup"]("r9c0") is None and m["lookup"]("bad") is None

def test_csv_utf8_quoted_and_escaped(tmp_path):
    sp = _mod("sheet_parser")
    p = tmp_path / "q.csv"
    p.write_text('名字,说明\n"甲,乙","含""引号"""\n', encoding="utf-8")
    m = sp.parse_csv(str(p))
    assert m["sheets"][0]["rows"][1][0]["text"] == "甲,乙"
    assert m["sheets"][0]["rows"][1][1]["text"] == '含"引号"'

def test_limits_flag_truncated(tmp_path):
    sp = _mod("sheet_parser")
    p = tmp_path / "wide.csv"
    p.write_text(",".join(f"c{i}" for i in range(210)) + "\n", encoding="utf-8")
    assert sp.parse_csv(str(p))["truncated"] is True
    from openpyxl import Workbook
    q = tmp_path / "big.xlsx"
    wb = Workbook()
    ws = wb.active
    for r in range(1, 2003):
        ws.cell(row=r, column=1, value=r)
    wb.save(str(q))
    assert sp.parse_xlsx(str(q))["truncated"] is True

def test_xlsx_datetime_and_time_formats(tmp_path):
    import datetime as dt

    sp = _mod("sheet_parser")
    from openpyxl import Workbook
    p = tmp_path / "dt.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["日期", "时间", "时刻"])
    ws.append([dt.datetime(2026, 1, 15), dt.time(9, 30), dt.datetime(2026, 3, 2, 14, 5)])
    ws.append([dt.date(2026, 2, 3), dt.time(9, 30, 15), "x"])
    wb.save(str(p))
    m = sp.parse_xlsx(str(p))
    rows = m["sheets"][0]["rows"]
    assert rows[1][0]["text"] == "2026-01-15"          # 零点 datetime 只显示日期
    assert rows[1][1]["text"] == "09:30"
    assert rows[1][2]["text"] == "2026-03-02 14:05"    # 非零点带时分
    assert rows[2][0]["text"] == "2026-02-03"          # date 只显示日期
    assert rows[2][1]["text"] == "09:30:15"
    b = m["lookup"]("s0!A2")
    assert b["text"] == "2026-01-15"                   # lookup 回填同一格式

def test_renderer_html_contract(tmp_path):
    sp, sr = _mod("sheet_parser"), _mod("sheet_renderer")
    hr = _mod("html_renderer")
    m = sp.parse_xlsx(str(_xlsx(tmp_path)))
    html = sr.render_sheet_html(m, restored=[{"anchor": "s0!B2", "comment": "核对", "seq": 1}])
    assert 'qrc:///qtwebchannel/qwebchannel.js' in html
    assert hr._BOOT_JS in html and hr._PICK_JS in html and hr._ANNOTATE_JS in html
    assert 'id="note-box"' in html
    assert 'data-anchor="s0!B2"' in html and "同比+5%" in html
    assert 'data-anchor="s0!table"' in html
    assert 'window.__showSheet' in html and 'class="tab active"' in html

def test_renderer_csv_table_anchor(tmp_path):
    sp, sr = _mod("sheet_parser"), _mod("sheet_renderer")
    p = tmp_path / "w.csv"
    p.write_text("城市,天气\n上海,晴\n", encoding="utf-8")
    html = sr.render_sheet_html(sp.parse_csv(str(p)))
    assert 'data-anchor="table"' in html and 'data-anchor="r1c0"' in html

def test_renderer_escapes_html(tmp_path):
    sp, sr = _mod("sheet_parser"), _mod("sheet_renderer")
    p = tmp_path / "esc.csv"
    p.write_text('x,<script>alert(1)</script>\nA & "B",ok\n', encoding="utf-8")
    html = sr.render_sheet_html(sp.parse_csv(str(p)))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html and 'A &amp; &quot;B&quot;' in html
