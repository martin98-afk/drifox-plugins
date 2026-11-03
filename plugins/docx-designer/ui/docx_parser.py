# -*- coding: utf-8 -*-
"""docx 解析：XML 流遍历 → 中间结构（纯函数，无 Qt 依赖）。

锚点约定：body 级块索引（str，0 起）；表格单元格 "idx:r{row}c{col}"（col 为网格列号）。
Block["runs"] 项三种形态：
- {"text": str, "bold"/"italic"/"underline": bool}
- {"image": data_uri}
- {"math": OMML XML 字符串}
已知简化：run 级样式只看直接 rPr（不做样式表继承）；嵌套表格降级忽略；
公式在 text 中以平文本呈现。
"""

import base64
import re

from docx import Document
from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

_HEADING_NAME_RE = re.compile(r"^(?:Heading|标题)\s*(\d+)$", re.I)
_HEADING_ID_RE = re.compile(r"^Heading\s*(\d+)$", re.I)


def docx_default_font(doc):
    """文档默认正文字体（styles.xml docDefaults；eastAsia 优先，其次 ascii）。"""
    try:
        return _default_font_from_styles_xml(doc.styles.element)
    except Exception:
        return None


def _default_font_from_styles_xml(styles_root):
    if styles_root is None:
        return None
    dd = styles_root.find(f"{{{W}}}docDefaults")
    if dd is None:
        return None
    rpr = dd.find(f"{{{W}}}rPrDefault/{{{W}}}rPr")
    if rpr is None:
        return None
    fonts = rpr.find(f"{{{W}}}rFonts")
    if fonts is None:
        return None
    return fonts.get(f"{{{W}}}eastAsia") or fonts.get(f"{{{W}}}ascii")


def parse_document(path):
    """解析 docx，返回 Block 列表（body 顺序，index 连续）。"""
    doc = Document(str(path))
    style_names = _style_name_map(doc)
    styles_map = _parse_styles(doc)
    numbering = _parse_numbering(doc)
    counter = _NumberingCounter()
    blocks = []
    body = doc.element.body
    doc_font, doc_size = _doc_defaults(doc)
    for child in body.iterchildren():
        try:
            local = etree.QName(child).localname
        except ValueError:
            continue
        if local == "p":
            blocks.append(
                _parse_paragraph(child, doc, len(blocks), style_names, styles_map,
                                 numbering, counter, doc_font, doc_size)
            )
        elif local == "tbl":
            blocks.append(_parse_table(child, doc, len(blocks), style_names))
    return blocks


def _style_name_map(doc):
    """styleId → 显示名（如 "Heading 1" / "标题 1"）。"""
    out = {}
    try:
        for s in doc.styles:
            try:
                out[s.style_id] = s.name or ""
            except Exception:
                continue
    except Exception:
        pass
    return out


def _heading_level(p, style_id, style_name):
    for pat, val in ((_HEADING_NAME_RE, style_name), (_HEADING_ID_RE, style_id)):
        m = pat.match((val or "").strip())
        if m:
            return max(1, min(4, int(m.group(1))))
    pPr = p.find(f"{{{W}}}pPr")
    if pPr is not None:
        o = pPr.find(f"{{{W}}}outlineLvl")
        if o is not None:
            try:
                return max(1, min(4, int(o.get(f"{{{W}}}val")) + 1))
            except (TypeError, ValueError):
                pass
    return 0


def _is_list(pPr, style_id, style_name):
    """列表判定：段落级 numPr，或样式为列表类（ListBullet/ListNumber/ListParagraph）。"""
    if pPr is not None and pPr.find(f"{{{W}}}numPr") is not None:
        return True
    for val in (style_id or "", style_name or ""):
        if val.lower().startswith("list"):
            return True
    return False


# ── 样式引擎：段落/字符属性提取与样式链合并 ──────────────

def _attr(el, tag, attr_val="val"):
    """安全取子元素属性值，缺失返回 None。"""
    if el is None:
        return None
    e = el.find(f"{{{W}}}{tag}")
    if e is None:
        return None
    return e.get(f"{{{W}}}{attr_val}")


def _twips_to_pt(val):
    try:
        return round(int(val) / 20.0, 1)
    except (TypeError, ValueError):
        return None


def _para_props(ppr):
    """w:pPr → 属性 dict（值为 pt 或原始字符串，None 表示未设）。"""
    if ppr is None:
        return {}
    out = {}
    jc = _attr(ppr, "jc")
    if jc:
        out["align"] = {"center": "center", "left": "left", "start": "left",
                        "right": "right", "end": "right", "both": "justify",
                        "justify": "justify"}.get(jc, jc)
    ind = ppr.find(f"{{{W}}}ind")
    if ind is not None:
        flc = ind.get(f"{{{W}}}firstLineChars")
        first = ind.get(f"{{{W}}}firstLine")
        left = ind.get(f"{{{W}}}left") or ind.get(f"{{{W}}}start")
        if flc:  # 首行缩进按字：以 10.5pt/字近似（渲染端字号覆盖时以 em 补正更准）
            out["first_line_chars"] = round(int(flc) / 100.0, 2)
        elif first:
            pt = _twips_to_pt(first)
            if pt is not None:
                out["first_line_pt"] = pt
        if left:
            pt = _twips_to_pt(left)
            if pt is not None:
                out["left_pt"] = pt
    sp = ppr.find(f"{{{W}}}spacing")
    if sp is not None:
        for key, attr in (("before_pt", "before"), ("after_pt", "after")):
            pt = _twips_to_pt(sp.get(f"{{{W}}}{attr}"))
            if pt is not None:
                out[key] = pt
        line = sp.get(f"{{{W}}}line")
        if line and sp.get(f"{{{W}}}lineRule", "auto") == "auto":
            try:
                out["line"] = round(int(line) / 240.0, 2)
            except ValueError:
                pass
    numpr = ppr.find(f"{{{W}}}numPr")
    if numpr is not None:
        out["numId"] = _attr(numpr, "numId")
        out["ilvl"] = _attr(numpr, "ilvl") or "0"
    return out


def _run_props(rpr):
    """w:rPr → 字符属性 dict（sz 为半点，转 pt）。"""
    if rpr is None:
        return {}
    out = _run_flags(rpr)
    sz = _attr(rpr, "sz")
    if sz:
        try:
            out["size_pt"] = int(sz) / 2.0
        except ValueError:
            pass
    color = _attr(rpr, "color")
    if color and color != "auto":
        out["color"] = f"#{color}"
    fonts = rpr.find(f"{{{W}}}rFonts")
    if fonts is not None:
        ea = fonts.get(f"{{{W}}}eastAsia")
        asc = fonts.get(f"{{{W}}}ascii")
        if ea:
            out["font_east"] = ea
        if asc:
            out["font_ascii"] = asc
    return out


def _parse_styles(doc):
    """styles.xml → {styleId: {name, basedOn, p, r}}。"""
    out = {}
    try:
        root = doc.styles.element
    except Exception:
        return out
    for st in root.findall(f"{{{W}}}style"):
        sid = st.get(f"{{{W}}}styleId") or ""
        if not sid:
            continue
        entry = {"name": "", "basedOn": None, "p": {}, "r": {}}
        entry["name"] = _attr(st, "name") or ""
        entry["basedOn"] = _attr(st, "basedOn")
        entry["p"] = _para_props(st.find(f"{{{W}}}pPr"))
        entry["r"] = _run_props(st.find(f"{{{W}}}rPr"))
        out[sid] = entry
    return out


def _resolve_style_chain(style_id, styles_map, max_depth=10):
    """basedOn 链上溯合并（基类先，子类覆盖）。返回 (段落属性, 字符属性)。"""
    merged_p, merged_r = {}, {}
    sid, depth = style_id, 0
    seen = set()
    while sid and sid in styles_map and sid not in seen and depth < max_depth:
        seen.add(sid)
        entry = styles_map[sid]
        for k, v in reversed(list(entry["p"].items())):
            if v is not None:
                merged_p[k] = v
        for k, v in reversed(list(entry["r"].items())):
            if v is not None:
                merged_r[k] = v
        sid = entry["basedOn"]
        depth += 1
    # reversed(list(...)) 使子类覆盖基类：逐条 update 即可，
    # 但按链序正向 update 已保证覆盖；上面的 reversed 是多余保险，语义等价
    return merged_p, merged_r


def _doc_defaults(doc):
    """docDefaults → (默认字体, 默认字号pt, 段落默认)。"""
    font = size_pt = None
    try:
        root = doc.styles.element
        dd = root.find(f"{{{W}}}docDefaults")
        rpr = dd.find(f"{{{W}}}rPrDefault/{{{W}}}rPr") if dd is not None else None
        if rpr is not None:
            props = _run_props(rpr)
            font = props.get("font_east") or props.get("font_ascii")
            size_pt = props.get("size_pt")
    except Exception:
        pass
    return font, size_pt


def _parse_numbering(doc):
    """numbering.xml → {numId: {ilvl: {fmt, text, first_pt, left_pt}}}（抽象编号已展开）。"""
    try:
        for rel in doc.part.rels.values():
            if rel.reltype.endswith("/numbering"):
                part = rel.target_part
                root = getattr(part, "element", None)
                if root is None:
                    return {}
                break
        else:
            return {}
    except Exception:
        return {}
    abstracts = {}
    for an in root.findall(f"{{{W}}}abstractNum"):
        aid = an.get(f"{{{W}}}abstractNumId")
        lvls = {}
        for lvl in an.findall(f"{{{W}}}lvl"):
            try:
                ilvl = int(lvl.get(f"{{{W}}}ilvl") or 0)
            except ValueError:
                continue
            fmt = _attr(lvl, "numFmt") or "decimal"
            txt = _attr(lvl, "lvlText") or "%1."
            ind = lvl.find(f"{{{W}}}pPr/{{{W}}}ind")
            first_pt = left_pt = None
            if ind is not None:
                first_pt = _twips_to_pt(ind.get(f"{{{W}}}first"))
                left_pt = _twips_to_pt(ind.get(f"{{{W}}}left") or ind.get(f"{{{W}}}start"))
            lvls[ilvl] = {"fmt": fmt, "text": txt, "first_pt": first_pt, "left_pt": left_pt}
        abstracts[aid] = lvls
    nums = {}
    for n in root.findall(f"{{{W}}}num"):
        nid = n.get(f"{{{W}}}numId")
        a = n.find(f"{{{W}}}abstractNumId")
        if nid and a is not None:
            nums[nid] = a.get(f"{{{W}}}val")
    return {"nums": nums, "abstracts": abstracts}


class _NumberingCounter:
    """列表编号状态机：维护 (numId, ilvl) 计数，展开 lvlText 模板为编号文本。"""

    _SYMBOL_MAP = {"\uF0B7": "\u2022", "\uF0A7": "\u25AB", "\uF0D8": "\u27A4",
                   "\uF0FC": "\u2713", "\uF0A8": "\u2764"}

    def __init__(self):
        self.counters = {}

    @staticmethod
    def _format_num(n, fmt):
        if fmt == "lowerLetter":
            return "" if n <= 0 else chr(96 + ((n - 1) % 26) + 1)
        if fmt == "upperLetter":
            s = _NumberingCounter._format_num(n, "lowerLetter")
            return s.upper()
        if fmt == "lowerRoman":
            return _to_roman(n).lower()
        if fmt == "upperRoman":
            return _to_roman(n)
        if fmt == "chineseCounting" or fmt == "chineseLegalSimplified":
            return _to_chinese(n)
        return str(n)  # decimal 及未知格式

    def next(self, numbering, num_id, ilvl):
        nums = numbering.get("nums") or {}
        abstracts = numbering.get("abstracts") or {}
        aid = nums.get(num_id)
        lvls = abstracts.get(aid) or {}
        info = lvls.get(ilvl) or {}
        # 更深层级计数重置
        for key in [k for k in self.counters if k[0] == num_id and k[1] > ilvl]:
            del self.counters[key]
        key = (num_id, ilvl)
        self.counters[key] = self.counters.get(key, 0) + 1
        fmt = info.get("fmt", "decimal")
        text = info.get("text", "%1.")
        if fmt == "bullet":
            label = self._SYMBOL_MAP.get(text, text or "\u2022")
        else:
            def repl(m):
                lvl_idx = int(m.group(1)) - 1
                cnt = self.counters.get((num_id, lvl_idx), 1)
                sub_fmt = (lvls.get(lvl_idx) or {}).get("fmt", "decimal")
                return self._format_num(cnt, sub_fmt)
            label = re.sub(r"%(\d)", repl, text)
        return label, info


def _to_roman(n):
    vals = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
            (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = []
    for v, s in vals:
        while n >= v:
            out.append(s)
            n -= v
    return "".join(out) or "I"


def _to_chinese(n):
    digits = "零一二三四五六七八九"
    if n <= 0:
        return "零"
    if n < 10:
        return digits[n]
    if n == 10:
        return "十"
    if n < 20:
        return "十" + digits[n % 10]
    s = str(n)
    units = "", "十", "百", "千"
    out = ""
    for i, ch in enumerate(s):
        d = int(ch)
        unit = units[len(s) - i - 1]
        if d == 0:
            if not out.endswith("零"):
                out += "零"
        else:
            out += digits[d] + unit
    return out.rstrip("零")



def _parse_paragraph(p, doc, index, style_names, styles_map, numbering, counter, doc_font, doc_size):
    pPr = p.find(f"{{{W}}}pPr")
    style_id = ""
    if pPr is not None:
        ps = pPr.find(f"{{{W}}}pStyle")
        if ps is not None:
            style_id = ps.get(f"{{{W}}}val") or ""
    style_name = style_names.get(style_id, style_id)
    level = _heading_level(p, style_id, style_name)
    # 样式链合并：docDefaults < 样式链 < 段落直接格式
    sp, sr = _resolve_style_chain(style_id, styles_map)
    direct_p = _para_props(pPr)
    pmerged = dict(sp)
    pmerged.update({k: v for k, v in direct_p.items() if v is not None})
    pmerged.setdefault("font", doc_font)
    pmerged.setdefault("size_pt", doc_size)
    # 编号
    list_label = None
    num_id = pmerged.get("numId")
    is_list = (num_id is not None) or _is_list(pPr, style_id, style_name)
    if num_id is not None:
        try:
            ilvl = int(pmerged.get("ilvl") or 0)
        except ValueError:
            ilvl = 0
        list_label, lvl_info = counter.next(numbering, num_id, ilvl)
        if lvl_info.get("first_pt") and "first_line_pt" not in pmerged:
            pmerged["first_line_pt"] = lvl_info["first_pt"]
        if lvl_info.get("left_pt") and "left_pt" not in pmerged:
            pmerged["left_pt"] = lvl_info["left_pt"]
    runs, text = _parse_runs(p, doc, sr)
    has_image = any("image" in r for r in runs)
    if has_image and not text.strip():
        kind = "image"
    elif level:
        kind = "heading"
    else:
        kind = "paragraph"
    fmt = {k: v for k, v in pmerged.items() if k not in ("numId", "ilvl") and v is not None}
    block = {
        "kind": kind,
        "index": index,
        "anchor": str(index),
        "style": style_name,
        "level": level,
        "text": text,
        "runs": runs,
        "is_list": bool(is_list and not list_label),
        "list_label": list_label,
        "fmt": fmt,
    }
    if kind == "image":
        block["image"] = next(r["image"] for r in runs if "image" in r)
    return block


def _parse_runs(p, doc, base_r=None):
    """段落 → (runs, 纯文本)。base_r 为样式链字符属性（run 直接格式覆盖之）。"""
    runs = []
    texts = []

    def add_text(t, rpr):
        if not t:
            return
        flags = _run_flags(rpr)
        props = _run_props(rpr)
        item = {
            "text": t,
            "bold": bool(flags["bold"] or (base_r or {}).get("bold", False)),
            "italic": bool(flags["italic"] or (base_r or {}).get("italic", False)),
            "underline": bool(flags["underline"] or (base_r or {}).get("underline", False)),
        }
        for key in ("size_pt", "color", "font_east", "font_ascii"):
            v = props.get(key) or (base_r or {}).get(key)
            if v:
                item[key] = v
        runs.append(item)
        texts.append(t)

    def walk(elem):
        for node in elem:
            try:
                q = etree.QName(node)
            except ValueError:
                continue
            if q.namespace == M and q.localname in ("oMath", "oMathPara"):
                xml = etree.tostring(node, encoding="unicode")
                runs.append({"math": xml})
                texts.append(_omml_plain_text(node))
            elif q.namespace != W:
                continue
            elif q.localname == "r":
                rpr = node.find(f"{{{W}}}rPr")
                blip = node.find(f".//{{{A}}}blip")
                if blip is not None:
                    data_uri = _image_data_uri(doc, blip.get(f"{{{R}}}embed"))
                    if data_uri:
                        runs.append({"image": data_uri})
                for sub in node:
                    try:
                        sq = etree.QName(sub)
                    except ValueError:
                        continue
                    if sq.namespace != W:
                        continue
                    if sq.localname == "t":
                        add_text(sub.text or "", rpr)
                    elif sq.localname == "br":
                        add_text("\n", None)
                    elif sq.localname == "tab":
                        add_text("\t", None)
            elif q.localname in ("hyperlink", "smartTag"):
                walk(node)
            elif q.localname == "sdt":
                content = node.find(f"{{{W}}}sdtContent")
                if content is not None:
                    walk(content)

    walk(p)
    return runs, "".join(texts)


def _run_flags(rpr):
    if rpr is None:
        return {"bold": False, "italic": False, "underline": False}

    def _on(tag):
        e = rpr.find(f"{{{W}}}{tag}")
        if e is None:
            return False
        v = e.get(f"{{{W}}}val")
        return v not in ("0", "false", "none", "")

    u = rpr.find(f"{{{W}}}u")
    underline = u is not None and (u.get(f"{{{W}}}val") or "single") not in ("none", "0", "false")
    return {"bold": _on("b"), "italic": _on("i"), "underline": underline}


def _image_data_uri(doc, rid):
    if not rid:
        return None
    try:
        part = doc.part.rels[rid].target_part
        blob = part.blob
        ct = part.content_type or "image/png"
        return f"data:{ct};base64,{base64.b64encode(blob).decode('ascii')}"
    except Exception:
        return None


def _omml_plain_text(omath):
    return "".join(t.text or "" for t in omath.iter(f"{{{M}}}t"))


def _parse_table(tbl, doc, index, style_names):
    raw_rows = []
    for r_i, tr in enumerate(tbl.findall(f"{{{W}}}tr")):
        row_cells = []
        col = 0
        for tc in tr.findall(f"{{{W}}}tc"):
            tcPr = tc.find(f"{{{W}}}tcPr")
            colspan = 1
            vmerge = None
            if tcPr is not None:
                gs = tcPr.find(f"{{{W}}}gridSpan")
                if gs is not None:
                    try:
                        colspan = max(1, int(gs.get(f"{{{W}}}val") or "1"))
                    except ValueError:
                        colspan = 1
                vm = tcPr.find(f"{{{W}}}vMerge")
                if vm is not None:
                    vmerge = vm.get(f"{{{W}}}val") or "continue"
            runs, text = _cell_content(tc, doc)
            row_cells.append(
                {
                    "text": text,
                    "runs": runs,
                    "colspan": colspan,
                    "rowspan": 1,
                    "col": col,
                    "anchor": f"{index}:r{r_i}c{col}",
                    "_vmerge": vmerge,
                }
            )
            col += colspan
        raw_rows.append(row_cells)

    # 纵向合并：restart 格向下吞 continue 格（col 对齐）
    for r_i, row in enumerate(raw_rows):
        for cell in row:
            if cell.get("_vmerge") == "restart":
                span = 1
                c = cell["col"]
                for r2 in range(r_i + 1, len(raw_rows)):
                    cont = next(
                        (x for x in raw_rows[r2]
                         if x.get("_vmerge") == "continue" and x["col"] == c),
                        None,
                    )
                    if cont is None:
                        break
                    span += 1
                    cont["_drop"] = True
                cell["rowspan"] = span

    final_rows = []
    for row in raw_rows:
        kept = []
        for cell in row:
            cell.pop("_vmerge", None)
            if cell.pop("_drop", None):
                continue
            kept.append(cell)
        final_rows.append(kept)

    # 网格列宽（dxa/twips）供渲染端生成 colgroup
    col_widths = []
    grid = tbl.find(f"{{{W}}}tblGrid")
    if grid is not None:
        for gc in grid.findall(f"{{{W}}}gridCol"):
            try:
                col_widths.append(int(gc.get(f"{{{W}}}w") or 0))
            except ValueError:
                col_widths.append(0)

    return {
        "kind": "table",
        "index": index,
        "anchor": str(index),
        "style": "",
        "level": 0,
        "text": _table_plain_text(final_rows),
        "runs": [],
        "rows": final_rows,
        "is_list": False,
        "col_widths": col_widths,
    }


def _cell_content(tc, doc):
    """单元格 → (首段 runs, 各段落文本 join)。"""
    texts = []
    first_runs = None
    for p in tc.findall(f"{{{W}}}p"):
        runs, text = _parse_runs(p, doc)
        if first_runs is None and runs:
            first_runs = runs
        if text.strip():
            texts.append(text)
    return (first_runs or []), "\n".join(texts)


def _table_plain_text(rows):
    lines = []
    for row in rows:
        lines.append(" | ".join(c["text"].replace("\n", " ") for c in row))
    return "\n".join(lines)
