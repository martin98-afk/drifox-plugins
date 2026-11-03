# -*- coding: utf-8 -*-
"""pptx 中间结构 → HTML（固定画布绝对定位，拾取/标注 JS 复用 docx 实现）。"""

import json
from html import escape

from .html_renderer import _ANNOTATE_JS, _BOOT_JS, _PICK_JS

_CSS = (
    ":root { --accent: %(accent)s; } "
    "* { box-sizing: border-box; } "
    "html, body { margin: 0; padding: 0; } "
    "body { background: %(outer)s; font-family: 'Microsoft YaHei', sans-serif; } "
    ".deck { padding: 18px 0 30px; zoom: 1; } "
    ".slide { position: relative; margin: 16px auto; overflow: hidden; "
    "box-shadow: 0 2px 14px rgba(0,0,0,0.45); } "
    ".shp { position: absolute; overflow: hidden; } "
    ".shp.txt { display: flex; flex-direction: column; padding: 3.6pt 7.2pt; } "
    ".shp.txt > p { margin: 0; } "
    ".shp img { width: 100%%; height: 100%%; object-fit: contain; } "
    ".shp table { border-collapse: collapse; table-layout: fixed; width: 100%%; height: 100%%; } "
    ".shp td { border: 1px solid #8a8a8a; padding: 2pt 4pt; vertical-align: top; "
    "font-size: 12pt; color: #1a1a1a; overflow: hidden; } "
    ".unsupported { display: flex; align-items: center; justify-content: center; "
    "border: 1px dashed #b8860b; background: #fffbe6; color: #8a6d3b; font-size: 12pt; } "
    "body.pick [data-anchor] { cursor: crosshair; } "
    "body.pick [data-anchor]:hover { outline: 2px solid var(--accent); outline-offset: 1px; } "
    "body.annotate [data-anchor] { cursor: text; } "
    "body.annotate [data-anchor]:hover { outline: 2px dashed #e6a23c; outline-offset: 1px; } "
    "[data-anchor].annotated { outline: 2px solid rgba(230,162,60,0.55); } "
    ".amark { position: absolute; left: 0; top: 0; z-index: 5; display: inline-block; "
    "min-width: 1.3em; padding: 0 0.25em; border-radius: 3px; background: #e6a23c; "
    "color: #fff; font-size: 10pt; text-align: center; font-weight: bold; } "
    "#note-box { position: absolute; z-index: 99; background: #fffbe6; border: 1px solid #e6a23c; "
    "border-radius: 6px; padding: 8px; box-shadow: 0 3px 10px rgba(0,0,0,0.3); width: 280px; } "
    "#note-box textarea { width: 100%%; height: 54px; box-sizing: border-box; border: 1px solid #d9d9d9; "
    "border-radius: 4px; font-size: 12px; padding: 4px; resize: vertical; } "
    "#note-box .nbtns { margin-top: 6px; text-align: right; } "
    "#note-box button { border: 1px solid #d9d9d9; background: #fff; border-radius: 4px; "
    "padding: 2px 10px; margin-left: 6px; cursor: pointer; } "
    "#note-box button.primary { background: #e6a23c; color: #fff; border-color: #e6a23c; } "
    "#note-box button.danger { background: #d9534f; color: #fff; border-color: #d9534f; display: none; } "
)


def render_pptx_html(model, *, outer="#1d2533", accent="#66c6ff", restored=None):
    w, h = model.get("w_pt"), model.get("h_pt")
    slides = "".join(_render_slide(s, w, h) for s in model.get("slides") or [])
    css_vars = {"accent": accent, "outer": outer}
    restored_json = json.dumps(restored or [], ensure_ascii=False)
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f"<style>{_CSS % css_vars}</style>"
        '<script src="qrc:///qtwebchannel/qwebchannel.js"></script>'
        f"<script>{_BOOT_JS}</script>"
        f"<script>window.__restored = {restored_json};</script>"
        "</head><body>"
        f'<div class="deck" id="deck">{slides}</div>'
        '<div id="note-box" style="display:none">'
        '<textarea placeholder="输入对选中元素的注释…"></textarea>'
        '<div class="nbtns"><button class="danger" onclick="window.__deleteNote()">删除</button>'
        '<button onclick="window.__closeNote(false)">取消</button>'
        '<button class="primary" onclick="window.__closeNote(true)">保存注释</button></div></div>'
        f"<script>{_ANNOTATE_JS}</script>"
        f"<script>{_PICK_JS}</script></body></html>"
    )


def _render_slide(slide, w, h):
    w = w or 0
    h = h or 0
    bg = slide.get("bg") or "#ffffff"
    shapes = "".join(_render_shape(sh) for sh in slide.get("shapes") or [])
    return (
        f'<section class="slide" style="width:{w}pt;height:{h}pt;background:{bg}">'
        f"{shapes}</section>"
    )


def _render_shape(sh):
    st = (f"left:{sh['left']}pt;top:{sh['top']}pt;"
          f"width:{sh['width']}pt;height:{sh['height']}pt;")
    anchor = escape(sh["anchor"], quote=True)
    kind = sh.get("kind")
    if kind == "text":
        inner = _render_paras(sh.get("paras") or [])
        st += f"justify-content:{_valign(sh.get('valign'))};"
        klass = "shp txt"
    elif kind == "image":
        inner = f'<img src="{sh["src"]}" alt="">'
        klass = "shp img"
    elif kind == "table":
        inner = _render_table(sh)
        klass = "shp tbl"
    elif kind == "shape":
        if sh.get("fill"):
            st += f"background:{sh['fill']};"
        if sh.get("line"):
            st += f"border:1pt solid {sh['line']};"
        inner = ""
        klass = "shp shp-solid"
    else:
        inner = f'<div class="unsupported">{escape(sh.get("label") or "不支持")}</div>'
        klass = "shp unsupported-box"
    return f'<div class="{klass}" data-anchor="{anchor}" style="{st}">{inner}</div>'


def _valign(value):
    if value == "middle":
        return "center"
    if value == "bottom":
        return "flex-end"
    return "flex-start"


def _render_paras(paras):
    out = []
    for p in paras:
        style = []
        if p.get("align"):
            style.append(f"text-align:{p['align']}")
        if p.get("space_before_pt"):
            style.append(f"margin-top:{p['space_before_pt']}pt")
        if p.get("space_after_pt"):
            style.append(f"margin-bottom:{p['space_after_pt']}pt")
        if p.get("line"):
            style.append(f"line-height:{p['line']}")
        elif p.get("line_pt"):
            style.append(f"line-height:{p['line_pt']}pt")
        if p.get("level"):
            style.append(f"margin-left:{p['level'] * 18}pt")
        st = f' style="{";".join(style)}"' if style else ""
        inner = "".join(_render_run(r) for r in p.get("runs") or [])
        out.append(f"<p{st}>{inner}</p>")
    return "".join(out)


def _render_run(run):
    text = escape(run.get("text") or "")
    if not text:
        return ""
    style = []
    if run.get("size_pt"):
        style.append(f"font-size:{run['size_pt']:g}pt")
    if run.get("color"):
        style.append(f"color:{run['color']}")
    if run.get("font"):
        style.append(f"font-family:'{escape(str(run['font']).replace(chr(39), ''), quote=True)}'")
    if run.get("bold"):
        text = f"<strong>{text}</strong>"
    if run.get("italic"):
        text = f"<em>{text}</em>"
    if run.get("underline"):
        text = f"<u>{text}</u>"
    if style:
        text = f'<span style="{escape(";".join(style), quote=True)}">{text}</span>'
    return text


def _render_table(sh):
    widths = sh.get("col_widths") or []
    total = sum(w for w in widths if w)
    parts = []
    if total > 0:
        cols = "".join(
            f'<col style="width:{round(w * 100.0 / total, 1)}%">' if w else "<col>"
            for w in widths
        )
        parts.append(f"<colgroup>{cols}</colgroup>")
    for row in sh.get("rows") or []:
        parts.append("<tr>")
        for cell in row:
            parts.append(f'<td>{escape(cell.get("text") or "")}</td>')
        parts.append("</tr>")
    return "<table>" + "".join(parts) + "</table>"
