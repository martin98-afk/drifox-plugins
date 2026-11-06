# -*- coding: utf-8 -*-
"""中间结构 → 完整 HTML（纯函数，无 Qt 依赖）。

页面固定白纸黑字（Word 文档本色），外围背景随主题传入；
拾取态由 body.pick 驱动 CSS hover 高亮；QWebChannel 桥对象名固定 docxbridge。
"""

import json
from html import escape

from lxml import etree

M = "http://schemas.openxmlformats.org/officeDocument/2006/math"

_HEADING_TAGS = {1: "h1", 2: "h2", 3: "h3", 4: "h4"}

_CSS = (
    ":root { --doc-fs: 15px; --accent: %(accent)s; } "
    "* { box-sizing: border-box; } "
    "html, body { margin: 0; padding: 0; } "
    "body { background: %(outer)s; font-family: 'Microsoft YaHei', sans-serif; } "
    ".page { max-width: 860px; margin: 20px auto; background: #ffffff; color: #1a1a1a; "
    "padding: 56px 72px; box-shadow: 0 2px 12px rgba(0,0,0,0.35); "
    "font-size: var(--doc-fs); line-height: 1.75; "
    "font-family: %(page_font)s 'SimSun', 'Microsoft YaHei', serif; } "
    "h1, h2, h3, h4 { line-height: 1.35; color: #000; "
    "font-family: 'Microsoft YaHei', 'SimHei', sans-serif; } "
    "h1 { font-size: 1.52em; margin: 0.8em 0 0.45em; } "
    "h2 { font-size: 1.33em; margin: 0.75em 0 0.4em; } "
    "h3 { font-size: 1.19em; margin: 0.7em 0 0.35em; } "
    "h4 { font-size: 1.05em; margin: 0.6em 0 0.3em; } "
    "p { margin: 0.45em 0; } "
    "p.doc-p, h1.doc-p, h2.doc-p, h3.doc-p, h4.doc-p { margin: 0.35em 0; } "
    ".lnum { display: inline-block; margin-right: 0.45em; } "
    "img { max-width: 100%%; height: auto; } "
    "figure { margin: 0.8em 0; text-align: center; } "
    "table { border-collapse: collapse; margin: 0.6em 0; width: 100%%; } "
    "td, th { border: 1px solid #9c9c9c; padding: 4px 8px; vertical-align: top; } "
    "td > p.cp { margin: 0; } "
    "body.pick [data-anchor] { cursor: crosshair; } "
    "body.pick [data-anchor]:hover { outline: 2px solid var(--accent); "
    "outline-offset: 1px; background: %(tint)s; } "
    "body.annotate [data-anchor] { cursor: text; } "
    "body.annotate [data-anchor]:hover { outline: 2px dashed #e6a23c; "
    "outline-offset: 1px; background: rgba(230,162,60,0.08); } "
    "[data-anchor].annotated { background: rgba(230,162,60,0.16); } "
    ".amark { display: inline-block; min-width: 1.3em; margin-right: 0.3em; "
    "padding: 0 0.25em; border-radius: 3px; background: #e6a23c; color: #fff; "
    "font-size: 0.72em; text-align: center; font-weight: bold; vertical-align: 0.25em; } "
    ".sheet { position: relative; background: #ffffff; color: #1a1a1a; "
    "margin: 14px auto; box-shadow: 0 2px 14px rgba(0,0,0,0.4); "
    "font-size: var(--doc-fs); line-height: 1.65; overflow: hidden; } "
    ".sheet-head { position: absolute; text-align: left; "
    "color: #444; line-height: 1.3; overflow: hidden; } "
    ".sheet-head img { max-height: 36pt; max-width: 80%%; } "
    ".sheet-foot { position: absolute; text-align: left; "
    "color: #555; line-height: 1.3; overflow: hidden; } "
    ".pageno { position: absolute; text-align: center; "
    "color: #777; font-size: 0.72em; } "
    ".sheet-body { height: 100%%; overflow: hidden; } "
    "#note-box { position: fixed; z-index: 99; background: #fffbe6; border: 1px solid #e6a23c; "
    "border-radius: 6px; padding: 8px; box-shadow: 0 3px 10px rgba(0,0,0,0.3); width: 280px; } "
    "#note-box textarea { width: 100%%; height: 54px; box-sizing: border-box; border: 1px solid #d9d9d9; "
    "border-radius: 4px; font-size: 12px; padding: 4px; resize: vertical; } "
    "#note-box .nbtns { margin-top: 6px; text-align: right; } "
    "#note-box button { border: 1px solid #d9d9d9; background: #fff; border-radius: 4px; "
    "padding: 2px 10px; margin-left: 6px; cursor: pointer; } "
    "#note-box button.primary { background: #e6a23c; color: #fff; border-color: #e6a23c; } "
    "#note-box button.danger { background: #d9534f; color: #fff; border-color: #d9534f; display: none; } "
    ".mr { font-family: 'Cambria Math', 'Cambria', serif; font-style: italic; } "
    ".mrb { font-weight: bold; } "
    ".frac { display: inline-block; vertical-align: middle; text-align: center; margin: 0 2px; } "
    ".frac .num { display: block; border-bottom: 1px solid currentColor; padding: 0 4px; } "
    ".frac .den { display: block; padding: 0 4px; } "
    ".rad .radsig { border-top: 1px solid currentColor; padding: 0 2px; } "
    ".raddeg { font-size: 0.7em; vertical-align: super; margin-right: 1px; } "
    "sub, sup { font-size: 0.72em; } "
    ".nary .nlim { display: inline-flex; flex-direction: column; font-size: 0.72em; "
    "vertical-align: middle; line-height: 1.1; margin-left: -2px; } "
    ".mathbox { display: inline-block; border: 1px dashed #b8860b; background: #fffbe6; "
    "padding: 1px 6px; border-radius: 3px; font-family: 'Cambria Math', serif; } "
)

_BOOT_JS = (
    "window.onerror = function(msg){"
    " document.title = 'JS错误: ' + msg;"
    " if (window.__bridge && window.__bridge.report_error) window.__bridge.report_error(String(msg));"
    " return false; };"
    "if (window.qt && qt.webChannelTransport) {"
    " new QWebChannel(qt.webChannelTransport, function(ch) {"
    " window.__bridge = ch.objects.docxbridge; }); }"
)

_PICK_JS = (
    "document.addEventListener('click', function(ev){"
    " if (document.body.classList.contains('annotate')) {"
    "  var el2 = ev.target.closest('[data-anchor]');"
    "  if (el2) { ev.preventDefault(); ev.stopPropagation(); window.__openNote(el2); }"
    "  return; }"
    " var el = ev.target.closest('[data-anchor]');"
    " if (!el || !document.body.classList.contains('pick')) return;"
    " ev.preventDefault(); ev.stopPropagation();"
    " el.scrollIntoView({block: 'center'});"
    " var r = el.getBoundingClientRect();"
    " if (window.__bridge) window.__bridge.pick("
    " el.getAttribute('data-anchor'), r.left, r.top, r.width, r.height,"
    " (el.textContent || '').replace(/\\s+/g, ' ').slice(0, 200)); });"
    "document.addEventListener('keydown', function(ev){"
    " if (ev.key === 'Escape' && !window.__noteOpen && window.__bridge) window.__bridge.escape(); });"
)

_PAGINATE_JS = (
    "function _mkSheet(pg, idx){"
    " var s = document.createElement('section'); s.className = 'sheet';"
    " s.style.width = pg.w_pt + 'pt'; s.style.height = pg.h_pt + 'pt';"
    " var m = pg.mar || {};"
    " s.style.paddingTop = m.top + 'pt'; s.style.paddingBottom = m.bottom + 'pt';"
    " s.style.paddingLeft = m.left + 'pt'; s.style.paddingRight = m.right + 'pt';"
    " var head = document.createElement('div'); head.className = 'sheet-head';"
    " head.style.top = (m.header * 0.5) + 'pt'; head.style.left = m.left + 'pt'; head.style.right = m.right + 'pt';"
    " function fill(s2){ return String(s2).replace(/\\{\\{page\\}\\}/g, idx + 1); }"
    " if (pg.header && pg.header.html) { head.setAttribute('data-anchor', 'header'); head.innerHTML = fill(pg.header.html); }"
    " var foot = document.createElement('div'); foot.className = 'sheet-foot';"
    " foot.style.bottom = (m.footer * 0.5) + 'pt'; foot.style.left = m.left + 'pt'; foot.style.right = m.right + 'pt';"
    " if (pg.footer && pg.footer.html) { foot.setAttribute('data-anchor', 'footer'); foot.innerHTML = fill(pg.footer.html); }"
    " var pn = document.createElement('div'); pn.className = 'pageno';"
    " pn.style.bottom = '6pt'; pn.style.left = m.left + 'pt'; pn.style.right = m.right + 'pt';"
    " pn.textContent = '- ' + (idx + 1) + ' -';"
    " if (pg.footer && pg.footer.html && pg.footer.html.indexOf('{{page}}') >= 0) pn.style.display = 'none';"
    " var body = document.createElement('div'); body.className = 'sheet-body';"
    " s.appendChild(head); s.appendChild(foot); s.appendChild(pn); s.appendChild(body);"
    " return s; }"
    "function paginate(){"
    " var flow = document.getElementById('flow');"
    " var pagesEl = document.getElementById('pages');"
    " var kids = [];"
    " while (pagesEl.firstChild) {"
    "  var sheet = pagesEl.firstChild;"
    "  var bodies = sheet.querySelectorAll('.sheet-body');"
    "  bodies.forEach(function(bd){ while (bd.firstChild) kids.push(bd.removeChild(bd.firstChild)); });"
    "  pagesEl.removeChild(sheet); }"
    " while (flow.firstChild) kids.push(flow.removeChild(flow.firstChild));"
    " var pg = Object.assign({}, window.__page || {}, window.__hdrftr || {});"
    " var probe = _mkSheet(pg, 0); pagesEl.appendChild(probe);"
    " var pbody = probe.querySelector('.sheet-body');"
    " var pageH = pbody.clientHeight || 700;"
    " pagesEl.removeChild(probe);"
    " var cur = null, curBody = null, idx = 0;"
    " function newPage(){ cur = _mkSheet(pg, idx); curBody = cur.querySelector('.sheet-body');"
    "  pagesEl.appendChild(cur); idx += 1; }"
    " function _splitTable(tbl){"
    "  var colgroup = null;"
    "  for (var c = tbl.firstElementChild; c; c = c.nextElementSibling){"
    "   if (c.tagName === 'COLGROUP'){ colgroup = c; break; } }"
    "  var rows = [];"
    "  (function collect(p){"
    "   for (var ch = p.firstElementChild; ch; ch = ch.nextElementSibling){"
    "    var t = ch.tagName;"
    "    if (t === 'TR') rows.push(ch);"
    "    else if (t === 'TBODY' || t === 'THEAD' || t === 'TFOOT') collect(ch); } })(tbl);"
    "  if (rows.length < 2) return;"
    "  var totalCols = colgroup ? colgroup.querySelectorAll('col').length : 0;"
    "  function spanSafe(tr){"
    "   if (!totalCols) return true;"
    "   var cs = tr.querySelectorAll('td,th'), sum = 0;"
    "   for (var k = 0; k < cs.length; k++) sum += parseInt(cs[k].getAttribute('colspan') || '1', 10) || 1;"
    "   return sum >= totalCols; }"
    "  var curTb = document.createElement('tbody');"
    "  for (var ch = tbl.firstElementChild; ch; ){"
    "   var nx = ch.nextElementSibling;"
    "   if (ch.tagName !== 'COLGROUP') tbl.removeChild(ch);"
    "   ch = nx; }"
    "  tbl.appendChild(curTb);"
    "  function newContPage(firstRow){"
    "   newPage();"
    "   var t2 = tbl.cloneNode(false);"
    "   if (colgroup) t2.appendChild(colgroup.cloneNode(true));"
    "   curTb = document.createElement('tbody');"
    "   t2.appendChild(curTb);"
    "   curBody.appendChild(t2);"
    "   if (firstRow) curTb.appendChild(firstRow); }"
    "  function _splitRow(tr){"
    "   var tds = tr.querySelectorAll('td,th');"
    "   var tr2 = tr.cloneNode(false), td2s = [], i, c;"
    "   for (i = 0; i < tds.length; i++){"
    "    var d = tds[i].cloneNode(false); td2s.push(d); tr2.appendChild(d); }"
    "   var guard = 0, movedAny = false;"
    "   while (curBody.scrollHeight > pageH && guard++ < 400){"
    "    var moved = false;"
    "    for (i = tds.length - 1; i >= 0; i--){"
    "     var src = tds[i], last = null, n = 0;"
    "     for (c = src.firstElementChild; c; c = c.nextElementSibling){"
    "      if (c.tagName === 'P'){ n++; last = c; } }"
    "     if (n > 1 && last){"
    "      td2s[i].appendChild(src.removeChild(last)); moved = true; movedAny = true;"
    "      break; } }"
    "    if (!moved) break; }"
    "   return movedAny ? tr2 : null; }"
    "  function _drainOversize(){"
    "   var guard = 0;"
    "   while (curBody.scrollHeight > pageH && curTb.children.length === 1 && guard++ < 60){"
    "    var tr2 = _splitRow(curTb.lastElementChild);"
    "    if (!tr2) break;"
    "    newContPage(tr2); } }"
    "  var ri = 0;"
    "  while (ri < rows.length){"
    "   _drainOversize();"
    "   curTb.appendChild(rows[ri]);"
    "   if (curBody.scrollHeight > pageH){"
    "    if (curTb.children.length > 1){"
    "     var popped = [curTb.removeChild(curTb.lastElementChild)];"
    "     while (!spanSafe(popped[0]) && curTb.children.length > 1){"
    "      popped.unshift(curTb.removeChild(curTb.lastElementChild)); }"
    "     newContPage();"
    "     for (var p2 = 0; p2 < popped.length; p2++) curTb.appendChild(popped[p2]);"
    "     _drainOversize(); }"
    "    else { _drainOversize(); } }"
    "   ri += 1; } }"
    " newPage();"
    " for (var i = 0; i < kids.length; i++){"
    "  var el = kids[i];"
    "  if (el.getAttribute('data-before') === '1' && curBody.children.length > 0) newPage();"
    "  curBody.appendChild(el);"
    "  if (el.getAttribute('data-after') === '1' && i < kids.length - 1 && curBody.children.length > 1){"
    "   newPage(); }"
    "  else if (curBody.scrollHeight > pageH && el.tagName === 'TABLE'){"
    "   _splitTable(el); }"
    "  else if (curBody.scrollHeight > pageH && curBody.children.length > 1){"
    "   curBody.removeChild(el); newPage(); curBody.appendChild(el); } }"
    " var all = pagesEl.querySelectorAll('.pageno');"
    " all.forEach(function(pn, i){ pn.textContent = '- ' + (i + 1) + ' -'; });"
    " var total = pagesEl.querySelectorAll('.sheet').length;"
    " pagesEl.querySelectorAll('.shtext').forEach(function(h){"
    "  if (h.textContent.indexOf('{{pages}}') >= 0)"
    "   h.textContent = h.textContent.replace(/\\{\\{pages\\}\\}/g, total); }); }"
    "window.addEventListener('load', paginate);"
)

_ANNOTATE_JS = (
    "window.__annotations = window.__restored || [];"
    "window.__noteOpen = false;"
    "window.__markOf = function(el){"
    " for (var i = 0; i < el.children.length; i++)"
    "  if (el.children[i].classList && el.children[i].classList.contains('amark')) return el.children[i];"
    " return null; };"
    "window.__removeMark = function(el){ var m = window.__markOf(el); if (m) el.removeChild(m); };"
    "window.__markAll = function(anchor, seq, comment){"
    " document.querySelectorAll('[data-anchor=\"' + anchor + '\"]').forEach(function(el){"
    "  el.classList.add('annotated');"
    "  if (comment) el.title = comment;"
    "  var m = window.__markOf(el);"
    "  if (m) { m.textContent = seq; }"
    "  else { var mk = document.createElement('span'); mk.className = 'amark'; mk.textContent = seq; el.insertBefore(mk, el.firstChild); }"
    " }); };"
    "window.__unmarkAll = function(anchor){"
    " document.querySelectorAll('[data-anchor=\"' + anchor + '\"]').forEach(function(el){"
    "  el.classList.remove('annotated'); el.removeAttribute('title'); window.__removeMark(el); }); };"
    "window.__renumber = function(){"
    " window.__annotations.forEach(function(a, i){ a.seq = i + 1;"
    "  window.__markAll(a.anchor, a.seq, a.comment); }); };"
    "window.__openNote = function(el){"
    " var box = document.getElementById('note-box');"
    " window.__noteTarget = el;"
    " var existing = null;"
    " if (el.classList.contains('annotated')) {"
    "  var anc = el.getAttribute('data-anchor');"
    "  for (var i = 0; i < window.__annotations.length; i++)"
    "   if (window.__annotations[i].anchor === anc) existing = window.__annotations[i]; }"
    " box.setAttribute('data-editing', existing ? existing.anchor : '');"
    " var ta0 = box.querySelector('textarea');"
    " ta0.value = existing ? existing.comment : '';"
    " box.querySelector('.nbtns .primary').textContent = existing ? '更新注释' : '保存注释';"
    " box.querySelector('.nbtns .danger').style.display = existing ? 'inline-block' : 'none';"
    " var r0 = el.getBoundingClientRect();"
    " box.style.left = Math.max(8, Math.min(r0.left, window.innerWidth - 300)) + 'px';"
    " box.style.top = Math.max(8, Math.min(r0.bottom + 4, window.innerHeight - 100)) + 'px';"
    " box.style.display = 'block';"
    " window.__noteOpen = true;"
    " ta0.focus(); };"
    "window.__closeNote = function(commit){"
    " var box = document.getElementById('note-box');"
    " var ta = box.querySelector('textarea');"
    " var comment = ta.value.trim();"
    " var el = window.__noteTarget;"
    " var editing = box.getAttribute('data-editing') || '';"
    " box.style.display = 'none'; window.__noteOpen = false; window.__noteTarget = null;"
    " box.removeAttribute('data-editing');"
    " if (!commit || !el) return;"
    " var anchor = el.getAttribute('data-anchor');"
    " if (editing) {"
    "  if (!comment) return;"
    "  var a = null;"
    "  for (var i = 0; i < window.__annotations.length; i++)"
    "   if (window.__annotations[i].anchor === editing) a = window.__annotations[i];"
    "  if (a) { a.comment = comment; window.__markAll(editing, a.seq, comment);"
    "   if (window.__bridge && window.__bridge.annotate_updated)"
    "    window.__bridge.annotate_updated(editing, comment); }"
    "  return; }"
    " if (!comment) return;"
    " var seq = window.__annotations.length + 1;"
    " var snippet = (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 120);"
    " var r = el.getBoundingClientRect();"
    " window.__annotations.push({anchor: anchor, comment: comment, seq: seq, snippet: snippet});"
    " window.__markAll(anchor, seq, comment);"
    " if (window.__bridge && window.__bridge.annotate_added)"
    "  window.__bridge.annotate_added(anchor, comment, seq, snippet, r.left, r.top, r.width, r.height); };"
    "window.__deleteNote = function(){"
    " var box = document.getElementById('note-box');"
    " var anchor = box.getAttribute('data-editing') || '';"
    " box.style.display = 'none'; box.removeAttribute('data-editing');"
    " window.__noteOpen = false; window.__noteTarget = null;"
    " if (anchor) window.__removeAnnotation(anchor); };"
    "window.__removeAnnotation = function(anchor){"
    " window.__annotations = window.__annotations.filter(function(a){ return a.anchor !== anchor; });"
    " window.__unmarkAll(anchor);"
    " window.__renumber();"
    " if (window.__bridge && window.__bridge.annotate_deleted)"
    "  window.__bridge.annotate_deleted(anchor); };"
    "window.__clearAnnotations = function(){"
    " document.querySelectorAll('[data-anchor].annotated').forEach(function(el){"
    "  el.classList.remove('annotated'); el.removeAttribute('title'); window.__removeMark(el); });"
    " window.__annotations = []; };"
    "window.__restoreAnnotations = function(){"
    " (window.__restored || []).forEach(function(a, i){"
    "  a.seq = i + 1;"
    "  window.__markAll(a.anchor, a.seq, a.comment); }); };"
    "window.addEventListener('load', function(){ window.__restoreAnnotations(); });"
)

def render_html(blocks, *, outer="#1d2533", accent="#66c6ff", doc_font=None,
                page_setup=None, hdr_ftr=None, restored=None):
    tint = "rgba(102, 198, 255, 0.10)" if accent == "#66c6ff" else "rgba(0, 120, 212, 0.08)"
    body = "".join(_render_block(b) for b in blocks)
    if doc_font is None:  # 从块级 fmt 推断文档默认字体（docx_parser 已注入 docDefaults）
        for b in blocks:
            f = (b.get("fmt") or {}).get("font")
            if f:
                doc_font = f
                break
    safe_font = (doc_font or "").replace("'", "")
    page_font = f"'{safe_font}', " if safe_font else ""
    css_vars = {"accent": accent, "outer": outer, "tint": tint, "page_font": page_font}
    setup_json = json.dumps(page_setup or {}, ensure_ascii=False)
    hf_html = {}
    for kind in ("header", "footer"):
        v = (hdr_ftr or {}).get(kind) or {}
        hf_html[kind] = {"html": _render_hf(v.get("blocks"))}
    hdr_json = json.dumps(hf_html, ensure_ascii=False)
    restored_json = json.dumps(restored or [], ensure_ascii=False)
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f"<style>{_CSS % css_vars}</style>"
        '<script src="qrc:///qtwebchannel/qwebchannel.js"></script>'
        f"<script>{_BOOT_JS}</script>"
        '<script>window.__page = ' + setup_json + ';'
        'window.__hdrftr = ' + hdr_json + ';'
        'window.__restored = ' + restored_json + ';</script>'
        "</head><body>"
        f"<div id=\"flow\" style=\"display:none\">{body}</div>"
        "<div id=\"pages\"></div>"
        '<div id=\"note-box\" style=\"display:none\">'
        '<textarea placeholder="输入对选中元素的注释…"></textarea>'
        '<div class="nbtns"><button class="danger" onclick="window.__deleteNote()">删除</button>'
        '<button onclick="window.__closeNote(false)">取消</button>'
        '<button class="primary" onclick="window.__closeNote(true)">保存注释</button></div></div>'
        f"<script>{_PAGINATE_JS}</script>"
        f"<script>{_ANNOTATE_JS}</script>"
        f"<script>{_PICK_JS}</script></body></html>"
    )


def _fmt_style(f):
    """Block.fmt / run 属性 dict → 内联 CSS 片段。字号以 Word 五号 10.5pt 为基准转 em（保留缩放）。"""
    if not f:
        return ""
    parts = []
    if f.get("align"):
        parts.append(f"text-align:{f['align']}")
    if f.get("first_line_chars"):
        try:
            parts.append(f"text-indent:{float(f['first_line_chars']):g}em")
        except (TypeError, ValueError):
            pass
    elif f.get("first_line_pt"):
        parts.append(f"text-indent:{f['first_line_pt']}pt")
    if f.get("left_pt"):
        parts.append(f"margin-left:{f['left_pt']}pt")
    if f.get("before_pt"):
        parts.append(f"margin-top:{f['before_pt']}pt")
    if f.get("after_pt"):
        parts.append(f"margin-bottom:{f['after_pt']}pt")
    if f.get("line"):
        parts.append(f"line-height:{f['line']}")
    if f.get("size_pt"):
        try:
            parts.append(f"font-size:{round(float(f['size_pt']) / 10.5, 2)}em")
        except (TypeError, ValueError):
            pass
    if f.get("font") or f.get("font_east"):
        fname = (f.get("font") or f.get("font_east") or "").replace("'", "")
        if fname:
            parts.append(f"font-family:'{fname}'")
    if f.get("color"):
        parts.append(f"color:{f['color']}")
    for side, css in (f.get("borders") or {}).items():
        if side in ("top", "bottom", "left", "right"):
            parts.append(f"border-{side}:{css}")
    return (";".join(parts) + ";") if parts else ""


def _render_block(b):
    a = escape(b["anchor"], quote=True)
    kind = b["kind"]
    if kind == "table":
        return _render_table(b)
    brk = ""
    if b.get("page_break_before"):
        brk += ' data-before="1"'
    if b.get("page_break"):
        brk += ' data-after="1"'
    if kind == "image":
        style = _fmt_style(b.get("fmt"))
        st_attr = f' style="{escape(style, quote=True)}"' if style else ""
        return f'<figure data-anchor="{a}"{st_attr}{brk}><img src="{b["image"]}" alt=""></figure>'
    tag = _HEADING_TAGS.get(b.get("level") or 0, "h4") if kind == "heading" else "p"
    style = _fmt_style(b.get("fmt"))
    inner = _render_runs(b.get("runs"))
    if b.get("list_label"):
        inner = f'<span class="lnum">{escape(b["list_label"])}</span>{inner}'
    elif b.get("is_list"):
        inner = '<span class="lnum">&#8226;</span>' + inner
    st_attr = f' style="{escape(style, quote=True)}"' if style else ""
    return f'<{tag} class="doc-p" data-anchor="{a}"{st_attr}{brk}>{inner}</{tag}>'


def _render_runs(runs):
    out = []
    for r in runs or []:
        if "image" in r:
            w = r.get("width_pt")
            st = f"vertical-align:middle;width:{w}pt" if w else "vertical-align:middle"
            out.append(f'<img src="{r["image"]}" style="{st}">')
        elif "math" in r:
            out.append(_render_math(r["math"]))
        else:
            t = escape(r.get("text", ""))
            if not t:
                continue
            t = t.replace("\n", "<br>").replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;")
            style = _fmt_style({k: r[k] for k in ("size_pt", "color", "font_east") if r.get(k)})
            if r.get("bold"):
                t = f"<strong>{t}</strong>"
            if r.get("italic"):
                t = f"<em>{t}</em>"
            if r.get("underline"):
                t = f"<u>{t}</u>"
            if style:
                t = f'<span style="{escape(style, quote=True)}">{t}</span>'
            out.append(t)
    return "".join(out)


def _render_table(b):
    a = escape(b["anchor"], quote=True)
    widths = b.get("col_widths") or []
    total = sum(w for w in widths if w > 0)
    parts = [f'<table data-anchor="{a}">']
    if total > 0:
        cols = []
        for w in widths:
            pct = round(w * 100.0 / total, 1) if w > 0 else None
            cols.append(f'<col style="width:{pct}%">' if pct else "<col>")
        parts.append(f"<colgroup>{''.join(cols)}</colgroup>")
    for row in b["rows"]:
        parts.append("<tr>")
        for cell in row:
            attrs = f' data-anchor="{escape(cell["anchor"], quote=True)}"'
            if cell.get("colspan", 1) > 1:
                attrs += f' colspan="{cell["colspan"]}"'
            if cell.get("rowspan", 1) > 1:
                attrs += f' rowspan="{cell["rowspan"]}"'
            para_runs = cell.get("para_runs")
            if para_runs is not None:
                # 逐段落出块级 <p>：分页 JS 可在段落边界拆单行超高行
                inner = "".join(
                    f'<p class="cp">{_render_runs(pr)}</p>' for pr in para_runs if pr
                )
                if not inner:
                    inner = escape(cell.get("text", ""))
            else:
                inner = _render_runs(cell.get("runs")) or escape(cell.get("text", ""))
            parts.append(f"<td{attrs}>{inner}</td>")
        parts.append("</tr>")
    parts.append("</table>")
    return "".join(parts)


def _render_hf(blocks):
    """页眉/页脚结构化块 → HTML 片段（表格还原边框/列宽/合并）。"""
    out = []
    for b in blocks or []:
        if b.get("kind") == "tbl":
            out.append(_render_hf_table(b))
            continue
        style = _fmt_style(b.get("fmt"))
        st = f' style="{escape(style, quote=True)}"' if style else ""
        out.append(f"<p{st}>{_render_runs(b.get('runs'))}</p>")
    return "".join(out)

def _render_hf_table(b):
    widths = b.get("col_widths") or []
    total = sum(w for w in widths if w > 0)
    borders = b.get("borders") or {}
    css = []
    for side, key in (("top", "top"), ("bottom", "bottom"), ("left", "left"),
                      ("right", "right"), ("insideH", "bottom"), ("insideV", "right")):
        if side in borders:
            css.append(f"border-{key}:{borders[side]}")
    pad = b.get("cell_pad_pt") or 5.4
    td_style = f"padding:1pt {pad:g}pt;vertical-align:top;" + ";".join(css)
    parts = ['<table style="border-collapse:collapse;width:100%;table-layout:fixed;margin:0">']
    if total > 0:
        cols = "".join(
            f'<col style="width:{round(w * 100.0 / total, 1)}%">' if w > 0 else "<col>" for w in widths
        )
        parts.append(f"<colgroup>{cols}</colgroup>")
    for row in b.get("rows") or []:
        parts.append("<tr>")
        for cell in row:
            attrs = []
            if cell.get("colspan", 1) > 1:
                attrs.append(f'colspan="{cell["colspan"]}"')
            if cell.get("rowspan", 1) > 1:
                attrs.append(f'rowspan="{cell["rowspan"]}"')
            a = (" " + " ".join(attrs)) if attrs else ""
            inner = _render_runs(cell.get("runs")) or escape(cell.get("text", ""))
            parts.append(f'<td{a} style="{escape(td_style, quote=True)}">{inner}</td>')
        parts.append("</tr>")
    parts.append("</table>")
    return "".join(parts)

def _render_math(xml_str):
    try:
        el = etree.fromstring(xml_str.encode())
    except etree.XMLSyntaxError:
        return '<span class="mathbox">[公式]</span>'
    return f'<span class="doc-math">{omml_to_html(el)}</span>'


def _kids(el):
    """递归拼接子元素（含直接文本与 tail）。"""
    if el is None:
        return ""
    out = el.text or ""
    for c in el:
        if isinstance(c.tag, str):
            out += omml_to_html(c)
        if c.tail:
            out += escape(c.tail)
    return out


def omml_to_html(el):
    """OMML 元素 → HTML/CSS 模拟公式。未覆盖结构降级为其子内容的拼接。"""
    try:
        q = etree.QName(el)
    except ValueError:
        return ""
    if q.namespace != M:
        return _kids(el)
    t = q.localname
    if t == "r":
        txt = "".join(x.text or "" for x in el.findall(f"{{{M}}}t"))
        if not txt:
            return ""
        sty = el.find(f"{{{M}}}rPr/{{{M}}}sty")
        bold = sty is not None and sty.get(f"{{{M}}}val") == "b"
        cls = "mr mrb" if bold else "mr"
        return f'<span class="{cls}">{escape(txt)}</span>'
    if t == "f":
        return (
            '<span class="frac">'
            f'<span class="num">{_kids(el.find(f"{{{M}}}num"))}</span>'
            f'<span class="den">{_kids(el.find(f"{{{M}}}den"))}</span></span>'
        )
    if t == "sSub":
        return f'{_kids(el.find(f"{{{M}}}e"))}<sub>{_kids(el.find(f"{{{M}}}sub"))}</sub>'
    if t == "sSup":
        return f'{_kids(el.find(f"{{{M}}}e"))}<sup>{_kids(el.find(f"{{{M}}}sup"))}</sup>'
    if t == "sSubSup":
        return (
            f'{_kids(el.find(f"{{{M}}}e"))}'
            f'<sub>{_kids(el.find(f"{{{M}}}sub"))}</sub>'
            f'<sup>{_kids(el.find(f"{{{M}}}sup"))}</sup>'
        )
    if t == "rad":
        deghide = el.find(f"{{{M}}}radPr/{{{M}}}degHide") is not None
        deg = "" if deghide else f'<span class="raddeg">{_kids(el.find(f"{{{M}}}deg"))}</span>'
        return f'<span class="rad">{deg}&#8730;<span class="radsig">{_kids(el.find(f"{{{M}}}e"))}</span></span>'
    if t == "nary":
        chr_el = el.find(f"{{{M}}}naryPr/{{{M}}}chr")
        sym = chr_el.get(f"{{{M}}}val") if chr_el is not None else "&#8747;"
        sub = el.find(f"{{{M}}}sub")
        sup = el.find(f"{{{M}}}sup")
        lims = ""
        if sub is not None or sup is not None:
            lims = (
                '<span class="nlim">'
                f'<span>{_kids(sub)}</span><span>{_kids(sup)}</span></span>'
            )
        return f'<span class="nary">{sym}{lims}</span>{_kids(el.find(f"{{{M}}}e"))}'
    if t == "d":
        beg = el.find(f"{{{M}}}dPr/{{{M}}}begChr")
        end = el.find(f"{{{M}}}dPr/{{{M}}}endChr")
        b = beg.get(f"{{{M}}}val") if beg is not None else "("
        e = end.get(f"{{{M}}}val") if end is not None else ")"
        inner = "".join(_kids(x) for x in el.findall(f"{{{M}}}e"))
        return f"{escape(b)}{inner}{escape(e)}"
    return _kids(el)
