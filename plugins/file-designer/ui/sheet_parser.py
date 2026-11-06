# -*- coding: utf-8 -*-
"""Excel / CSV 解析（纯函数，无 Qt 依赖）。

xlsx / xlsm：openpyxl data_only=True 取缓存值，读合并单元格、列宽、多 sheet。
csv：编码链 utf-8-sig → utf-8 → gb18030 → latin-1，csv.Sniffer 探分隔符。

model：
  {"mode": "xlsx"|"csv", "source": 绝对路径, "sheets": [sheet], "truncated": bool,
   "lookup": callable}
sheet = {"name", "rows": [[cell]], "col_widths": [px], "merges": [{"r","c","rs","cs"}]}
cell = {"text", "anchor"}；lookup 返回 sheet_cell / sheet_table 结构（见 pick_format）。

锚点：xlsx s{sheet}!{列字母}{行号}（行列 1 起）；csv r{行}c{列}（0 起）/ table。
"""

import csv
import io
from pathlib import Path

MAX_XLSX_ROWS = 2000
MAX_XLSX_COLS = 200
MAX_CSV_ROWS = 5000
MAX_CSV_COLS = 200

_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "latin-1")


def _col_letter(n):
    """1 → A, 27 → AA。"""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _text(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _row_text(cells):
    return " | ".join((c.get("text") or "").replace("\n", " ").strip() for c in cells)


def _decode_csv(raw):
    last = None
    for enc in _ENCODINGS:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError as ex:
            last = ex
    raise ValueError(f"CSV 编码无法识别: {last}")


def _sniff(sample):
    try:
        d = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return d.delimiter
    except csv.Error:
        first = sample.splitlines()[0] if sample.splitlines() else ""
        for ch in ("\t", ";", "|", ","):
            if ch in first:
                return ch
        return ","


def parse_csv(path):
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    text, _enc = _decode_csv(p.read_bytes())
    delim = _sniff(text[:4096])
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delim)
    rows, truncated = [], False
    for r_i, raw_row in enumerate(reader):
        if r_i >= MAX_CSV_ROWS:
            truncated = True
            break
        cells = []
        for c_i, val in enumerate(raw_row[:MAX_CSV_COLS]):
            cells.append({"text": str(val).strip(), "anchor": f"r{r_i}c{c_i}"})
        if len(raw_row) > MAX_CSV_COLS:
            truncated = True
        rows.append(cells)
    if not rows:
        rows = [[]]
    sheet = {"name": p.name, "rows": rows, "col_widths": [], "merges": []}

    def lookup(anchor):
        if anchor == "table":
            return {"mode": "csv", "kind": "sheet_table", "rows": rows,
                    "sheet": p.name, "anchor": "table"}
        if not (isinstance(anchor, str) and anchor.startswith("r") and "c" in anchor):
            return None
        try:
            r_part, c_part = anchor[1:].split("c", 1)
            r_i, c_i = int(r_part), int(c_part)
        except ValueError:
            return None
        if r_i < 0 or c_i < 0 or r_i >= len(rows) or c_i >= len(rows[r_i]):
            return None
        header = ""
        if rows and c_i < len(rows[0]):
            header = rows[0][c_i]["text"]
        return {
            "mode": "csv", "kind": "sheet_cell", "anchor": anchor,
            "text": rows[r_i][c_i]["text"], "header": header,
            "sheet": p.name, "row_text": _row_text(rows[r_i]),
        }

    return {"mode": "csv", "source": str(p), "sheets": [sheet],
            "truncated": truncated, "lookup": lookup}


def parse_xlsx(path):
    try:
        from openpyxl import load_workbook
    except ImportError as ex:
        raise ImportError("缺少 openpyxl，无法解析 xlsx/xlsm") from ex
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    wb = load_workbook(str(p), data_only=True, read_only=False)
    sheets, truncated = [], False
    index = {}
    try:
        for s_i, ws in enumerate(wb.worksheets):
            max_r = min(ws.max_row or 0, MAX_XLSX_ROWS)
            max_c = min(ws.max_column or 0, MAX_XLSX_COLS)
            if (ws.max_row or 0) > MAX_XLSX_ROWS or (ws.max_column or 0) > MAX_XLSX_COLS:
                truncated = True
            merges = []
            merged_map = {}
            merged_ranges = getattr(ws, "merged_cells", None)
            for rng in (merged_ranges.ranges if merged_ranges else []):
                r0, c0 = rng.min_row - 1, rng.min_col - 1
                rs, cs = rng.max_row - rng.min_row + 1, rng.max_col - rng.min_col + 1
                if r0 >= max_r or c0 >= max_c:
                    continue
                merges.append({"r": r0, "c": c0, "rs": rs, "cs": cs})
                for rr in range(r0, min(r0 + rs, max_r)):
                    for cc in range(c0, min(c0 + cs, max_c)):
                        if (rr, cc) != (r0, c0):
                            merged_map[(rr, cc)] = (r0, c0)
            col_widths = []
            for c in range(1, max_c + 1):
                letter = _col_letter(c)
                dim = ws.column_dimensions.get(letter)
                w = float(dim.width or 0) if dim is not None else 0
                col_widths.append(max(72, min(320, int((w or 10) * 7.5))))
            rows = []
            for r in range(1, max_r + 1):
                cells = []
                for c in range(1, max_c + 1):
                    anchor = f"s{s_i}!{_col_letter(c)}{r}"
                    if (r - 1, c - 1) in merged_map:
                        cells.append({"text": "", "anchor": anchor, "covered": True})
                        continue
                    v = ws.cell(row=r, column=c).value
                    cells.append({"text": _text(v), "anchor": anchor})
                    index[anchor] = {
                        "mode": "xlsx", "kind": "sheet_cell", "anchor": anchor,
                        "text": _text(v), "sheet": ws.title, "row_text": "",
                        "header": _text(ws.cell(row=1, column=c).value),
                    }
                rows.append(cells)
            # 行文本与整表 lookup 在同一遍扫完后回填
            for r_i, cells in enumerate(rows):
                rt = _row_text(cells)
                for c_i, cell in enumerate(cells):
                    rec = index.get(cell["anchor"])
                    if rec is not None:
                        rec["row_text"] = rt
            sheets.append({"name": ws.title, "rows": rows,
                           "col_widths": col_widths, "merges": merges})
    finally:
        try:
            wb.close()
        except Exception:
            pass
    if not sheets:
        raise ValueError("工作簿里没有 sheet")

    for s_i, sh in enumerate(sheets):
        index[f"s{s_i}!table"] = {
            "mode": "xlsx", "kind": "sheet_table", "anchor": f"s{s_i}!table",
            "rows": sh["rows"], "sheet": sh["name"],
        }

    def lookup(anchor):
        return index.get(anchor)

    return {"mode": "xlsx", "source": str(p), "sheets": sheets,
            "truncated": truncated, "lookup": lookup}
