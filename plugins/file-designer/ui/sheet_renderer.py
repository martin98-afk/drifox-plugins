# -*- coding: utf-8 -*-
"""表格 model → HTML（纯函数，无 Qt 依赖）。

多 sheet 页内 tab 切换，冻结首行，合并单元格，列宽按字符估算。
每个 <td data-anchor> 可拾取可标注；整表标题带 data-anchor="table"。
"""

from .generic_renderer import e, wrap_html

_CSS = (
    ".wrap { padding: 14px 16px 30px; } "
    ".tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; } "
    ".tab { padding: 5px 14px; border: 1px solid rgba(128,128,128,0.45); "
    "border-radius: 5px 5px 0 0; background: rgba(255,255,255,0.10); color: #d7e2f0; "
    "cursor: pointer; font-size: 13px; } "
    ".tab.active { background: var(--accent); color: #101820; font-weight: bold; } "
    ".pane { display: none; background: #ffffff; border-radius: 6px; padding: 10px; "
    "overflow: auto; max-height: 78vh; box-shadow: 0 2px 12px rgba(0,0,0,0.35); } "
    ".pane.active { display: block; } "
    "table.grid { border-collapse: collapse; table-layout: fixed; font-size: 13px; } "
    "table.grid th, table.grid td { border: 1px solid #b7c0cc; padding: 4px 7px; "
    "text-align: left; vertical-align: top; overflow-wrap: break-word; } "
    "table.grid thead th { position: sticky; top: 0; z-index: 2; background: #e8eef6; "
    "color: #1a2a3a; font-weight: bold; } "
    "table.grid td.covered { display: none; } "
    ".rowno { background: #f2f5f9; color: #7a889a; text-align: center; width: 46px; } "
    ".warn { color: #ffd37a; margin: 8px 0 12px; font-size: 13px; } "
    ".sheet-caption { color: #d7e2f0; font-size: 13px; margin: 0 0 8px; } "
)

_TABS_JS = (
    "window.__showSheet = function(i){"
    " document.querySelectorAll('.tab').forEach(function(t, j){"
    "  t.classList.toggle('active', j === i); });"
    " document.querySelectorAll('.pane').forEach(function(p, j){"
    "  p.classList.toggle('active', j === i); }); };"
)


def _cell_html(cell, tag="td"):
    cls = ""
    span = ""
    if cell.get("covered"):
        cls = ' class="covered"'
    if cell.get("rs") and cell["rs"] > 1:
        span += f' rowspan="{cell["rs"]}"'
    if cell.get("cs") and cell["cs"] > 1:
        span += f' colspan="{cell["cs"]}"'
    return (
        f'<{tag}{span} data-anchor="{e(cell.get("anchor"))}"{cls}>'
        f'{e(cell.get("text"))}</{tag}>'
    )


def _apply_merges(sheet):
    """把 merges 的 rs/cs 挂到左上角单元格，被覆盖格标 covered。"""
    rows = [list(r) for r in sheet["rows"]]
    for m in sheet.get("merges") or []:
        r, c = m["r"], m["c"]
        if r < len(rows) and c < len(rows[r]):
            rows[r][c]["rs"] = m["rs"]
            rows[r][c]["cs"] = m["cs"]
    return rows


def _render_pane(sheet, s_i, mode, active):
    rows = _apply_merges(sheet)
    widths = sheet.get("col_widths") or []
    cols = ""
    if widths:
        cols = "<colgroup><col style='width:46px'>" + "".join(
            f"<col style='width:{w}px'>" for w in widths
        ) + "</colgroup>"
    cap_anchor = "table" if mode == "csv" else f"s{s_i}!table"
    body = []
    for r_i, row in enumerate(rows):
        tag = "th" if r_i == 0 else "td"
        cells = "".join(_cell_html(c, tag) for c in row)
        body.append(f'<tr><td class="rowno">{r_i + 1}</td>{cells}</tr>')
    head = (
        f'<div class="sheet-caption" data-anchor="{e(cap_anchor)}">'
        f'{e(sheet.get("name"))} · 共 {len(rows)} 行（点击整行标题可拾取全表）</div>'
    )
    return (
        f'<div class="pane{" active" if active else ""}" data-sheet="{s_i}">'
        f"{head}<table class=\"grid\">{cols}<tbody>{''.join(body)}</tbody></table></div>"
    )


def render_sheet_html(model, *, outer="#1d2533", accent="#66c6ff", restored=None):
    sheets = model.get("sheets") or []
    mode = model.get("mode") or "xlsx"
    parts = []
    if model.get("truncated"):
        cap = "2000 行 × 200 列" if mode == "xlsx" else "5000 行 × 200 列"
        parts.append(f'<div class="warn">内容超过上限（{cap}）已截断</div>')
    if len(sheets) > 1:
        tabs = "".join(
            f'<div class="tab{" active" if i == 0 else ""}" '
            f'onclick="window.__showSheet({i})">{e(sh.get("name"))}</div>'
            for i, sh in enumerate(sheets)
        )
        parts.append(f'<div class="tabs">{tabs}</div>')
    parts.extend(
        _render_pane(sh, i, mode, i == 0) for i, sh in enumerate(sheets)
    )
    return wrap_html(
        f'<div class="wrap">{"".join(parts)}</div>',
        outer=outer, accent=accent, restored=restored,
        extra_css=_CSS, extra_js=_TABS_JS,
    )
