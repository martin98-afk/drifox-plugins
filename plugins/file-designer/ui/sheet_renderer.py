# -*- coding: utf-8 -*-
"""表格 model → HTML（纯函数，无 Qt 依赖）。

多 sheet 页内 tab 切换，冻结首行，合并单元格，列宽按字符估算。
每个 <td data-anchor> 可拾取可标注；整表标题带 data-anchor="table"。
"""

from .generic_renderer import _VIEW_JS, e, ink_for, wrap_html

_CSS = (
    "html, body { height: 100%%; } "
    ".wrap { height: 100%%; box-sizing: border-box; padding: 10px 12px 12px; "
    "display: flex; flex-direction: column; } "
    ".tabs { flex: 0 0 auto; display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; } "
    ".tab { padding: 5px 14px; border: 1px solid rgba(128,128,128,0.45); "
    "border-radius: 5px 5px 0 0; background: rgba(255,255,255,0.10); color: %(ink)s; "
    "cursor: pointer; font-size: 13px; } "
    ".tab.active { background: var(--accent); color: %(tab_active_ink)s; font-weight: bold; } "
    ".pane { display: none; background: #ffffff; border-radius: 6px; padding: 10px; "
    "overflow: auto; box-shadow: 0 2px 12px rgba(0,0,0,0.35); font-size: 13px; } "
    ".pane.active { display: block; flex: 1 1 0; min-height: 0; } "
    "table.grid { border-collapse: collapse; table-layout: fixed; width: 100%%; } "
    "table.grid th, table.grid td { border: 1px solid #b7c0cc; padding: 4px 7px; "
    "text-align: left; vertical-align: top; overflow-wrap: break-word; } "
    "table.grid thead th { position: sticky; top: 0; z-index: 2; background: #e8eef6; "
    "color: #1a2a3a; font-weight: bold; } "
    "table.grid td.covered { display: none; } "
    ".rowno { background: #f2f5f9; color: #7a889a; text-align: center; width: 46px; } "
    ".warn { flex: 0 0 auto; color: %(warn)s; margin: 4px 0 8px; font-size: 13px; } "
    ".sheet-caption { flex: 0 0 auto; color: #6b7a90; font-size: 12px; margin: 0 0 6px; } "
)

_TABS_JS = (
    "window.__showSheet = function(i){"
    " document.querySelectorAll('.tab').forEach(function(t, j){"
    "  t.classList.toggle('active', j === i); });"
    " document.querySelectorAll('.pane').forEach(function(p, j){"
    "  p.classList.toggle('active', j === i); }); };"
    "window.__setZoom = function(z){"
    " z = Math.max(0.6, Math.min(2.2, z));"
    " document.querySelectorAll('.pane').forEach(function(p){"
    "  p.style.fontSize = (13 * z).toFixed(1) + 'px'; }); };"
    "document.querySelectorAll('.pane').forEach(function(p){ window.__enableDrag(p); });"
)

def _est_col_widths(rows):
    """无原生列宽（csv）时按字符宽度估算（中文 12px / 英文 7.2px，前 200 行采样）。"""
    n_cols = max((len(r) for r in rows), default=0)
    widths = []
    for c_i in range(n_cols):
        w = 0.0
        for r in rows[:200]:
            if c_i < len(r):
                t = r[c_i].get("text") or ""
                w = max(w, sum(12.0 if ord(ch) > 0x2E80 else 7.2 for ch in t[:60]))
        widths.append(max(64, min(320, int(w) + 16)))
    return widths


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
    widths = sheet.get("col_widths") or _est_col_widths(rows)
    total = sum(widths) or 1
    cols = "<colgroup><col style='width:46px'>" + "".join(
        f"<col style='width:calc((100% - 46px) * {w / total:.4f})'>" for w in widths
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
    table_style = f" style='min-width:{total + 46}px'"
    return (
        f'<div class="pane{" active" if active else ""}" data-sheet="{s_i}">'
        f"{head}<table class=\"grid\"{table_style}>{cols}<tbody>{''.join(body)}</tbody></table></div>"
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
    css = _CSS % {
        "ink": ink_for(outer),
        "warn": ink_for(outer, "#ffd37a", "#a8700a"),
        "tab_active_ink": ink_for(outer, "#101820", "#ffffff"),
    }
    return wrap_html(
        f'<div class="wrap">{"".join(parts)}</div>',
        outer=outer, accent=accent, restored=restored,
        extra_css=css, extra_js=_VIEW_JS + _TABS_JS,
    )
