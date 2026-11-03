# -*- coding: utf-8 -*-
"""中间结构 → 完整 HTML（纯函数，无 Qt 依赖）。

页面固定白纸黑字（Word 文档本色），外围背景随主题传入；
拾取态由 body.pick 驱动 CSS hover 高亮；QWebChannel 桥对象名固定 docxbridge。
"""

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
    "table { border-collapse: collapse; margin: 0.8em 0; width: 100%%; } "
    "td, th { border: 1px solid #9c9c9c; padding: 4px 8px; vertical-align: top; } "
    "body.pick [data-anchor] { cursor: crosshair; } "
    "body.pick [data-anchor]:hover { outline: 2px solid var(--accent); "
    "outline-offset: 1px; background: %(tint)s; } "
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
    "if (window.qt && qt.webChannelTransport) {"
    " new QWebChannel(qt.webChannelTransport, function(ch) {"
    " window.__bridge = ch.objects.docxbridge; }); }"
)

_PICK_JS = (
    "document.addEventListener('click', function(ev){"
    " var el = ev.target.closest('[data-anchor]');"
    " if (!el || !document.body.classList.contains('pick')) return;"
    " ev.preventDefault(); ev.stopPropagation();"
    " el.scrollIntoView({block: 'center'});"
    " var r = el.getBoundingClientRect();"
    " if (window.__bridge) window.__bridge.pick("
    " el.getAttribute('data-anchor'), r.left, r.top, r.width, r.height,"
    " (el.textContent || '').replace(/\\s+/g, ' ').slice(0, 200)); });"
    "document.addEventListener('keydown', function(ev){"
    " if (ev.key === 'Escape' && window.__bridge) window.__bridge.escape(); });"
)


def render_html(blocks, *, outer="#1d2533", accent="#66c6ff", doc_font=None):
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
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f"<style>{_CSS % css_vars}</style>"
        '<script src="qrc:///qtwebchannel/qwebchannel.js"></script>'
        f"<script>{_BOOT_JS}</script>"
        f"</head><body><div class=\"page\">{body}</div>"
        f"<script>{_PICK_JS}</script></body></html>"
    )


def _fmt_style(f):
    """Block.fmt / run 属性 dict → 内联 CSS 片段。字号以 Word 五号 10.5pt 为基准转 em（保留缩放）。"""
    if not f:
        return ""
    parts = []
    if f.get("align"):
        parts.append(f"text-align:{f['align']}")
    if f.get("first_line_pt"):
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
    return (";".join(parts) + ";") if parts else ""


def _render_block(b):
    a = escape(b["anchor"], quote=True)
    kind = b["kind"]
    if kind == "table":
        return _render_table(b)
    if kind == "image":
        style = _fmt_style(b.get("fmt"))
        st_attr = f' style="{escape(style, quote=True)}"' if style else ""
        return f'<figure data-anchor="{a}"{st_attr}><img src="{b["image"]}" alt=""></figure>'
    tag = _HEADING_TAGS.get(b.get("level") or 0, "h4") if kind == "heading" else "p"
    style = _fmt_style(b.get("fmt"))
    inner = _render_runs(b.get("runs"))
    if b.get("list_label"):
        inner = f'<span class="lnum">{escape(b["list_label"])}</span>{inner}'
    elif b.get("is_list"):
        inner = '<span class="lnum">&#8226;</span>' + inner
    st_attr = f' style="{escape(style, quote=True)}"' if style else ""
    return f'<{tag} class="doc-p" data-anchor="{a}"{st_attr}>{inner}</{tag}>'


def _render_runs(runs):
    out = []
    for r in runs or []:
        if "image" in r:
            out.append(f'<img src="{r["image"]}" style="vertical-align:middle;">')
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
            inner = _render_runs(cell.get("runs")) or escape(cell.get("text", ""))
            parts.append(f"<td{attrs}>{inner}</td>")
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
