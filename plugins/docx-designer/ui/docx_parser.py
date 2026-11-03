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
V = "urn:schemas-microsoft-com:vml"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"

_HEADING_NAME_RE = re.compile(r"^(?:Heading|标题)\s*(\d+)$", re.I)
_HEADING_ID_RE = re.compile(r"^Heading\s*(\d+)$", re.I)

# 样式合并哨兵：显式清除继承值（如空 <w:ind/> 重置首行缩进）
_CLEAR = object()


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
    default_pid = _default_paragraph_style(doc)
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
                                 numbering, counter, doc_font, doc_size, default_pid)
            )
        elif local == "tbl":
            blocks.append(_parse_table(child, doc, len(blocks), style_names))
    return blocks


def docx_page_setup(path):
    """sectPr → 页面尺寸与边距（pt）。缺省 A4（595×842pt，边距 1in）"""
    setup = {
        "w_pt": 595.0, "h_pt": 842.0,
        "mar": {"top": 72.0, "right": 72.0, "bottom": 72.0, "left": 72.0,
                "header": 35.0, "footer": 35.0},
    }
    try:
        doc = Document(str(path))
        body = doc.element.body
        sect = body.find(f"{{{W}}}sectPr")
        if sect is None:
            return setup
        pgsz = sect.find(f"{{{W}}}pgSz")
        if pgsz is not None:
            w = _twips_to_pt(pgsz.get(f"{{{W}}}w"))
            h = _twips_to_pt(pgsz.get(f"{{{W}}}h"))
            if w and h:
                setup["w_pt"], setup["h_pt"] = w, h
        mar = sect.find(f"{{{W}}}pgMar")
        if mar is not None:
            for key, attr in (("top", "top"), ("right", "right"), ("bottom", "bottom"),
                              ("left", "left"), ("header", "header"), ("footer", "footer")):
                pt = _twips_to_pt(mar.get(f"{{{W}}}{attr}"))
                if pt is not None:
                    setup["mar"][key] = pt
    except Exception:
        pass
    return setup


def _local(el):
    try:
        return etree.QName(el).localname
    except ValueError:
        return ""

def _hf_paragraph(p, part, styles_map, doc_font, doc_size, default_style_id=""):
    """页眉/页脚段落 → ({kind:p, fmt, runs}, 纯文本)。"""
    pPr = p.find(f"{{{W}}}pPr")
    style_id = ""
    if pPr is not None:
        ps = pPr.find(f"{{{W}}}pStyle")
        if ps is not None:
            style_id = ps.get(f"{{{W}}}val") or ""
    if not style_id:
        style_id = default_style_id
    sp, sr = _resolve_style_chain(style_id, styles_map)
    fmt = _merge_para_fmt(sp, _para_props(pPr), doc_font, doc_size)
    fmt = {k: v for k, v in fmt.items() if v is not None and v is not _CLEAR}
    runs, text = _parse_runs(p, part, sr)
    return {"kind": "p", "fmt": fmt, "runs": runs}, text

def _hf_table(tbl, part):
    """页眉/页脚表格 → {kind:tbl, rows, col_widths, borders, cell_pad_pt}。"""
    rows, col_widths = _table_rows(tbl, part)
    borders, cell_pad = {}, 5.4
    tblPr = tbl.find(f"{{{W}}}tblPr")
    if tblPr is not None:
        bd = tblPr.find(f"{{{W}}}tblBorders")
        if bd is not None:
            borders = _parse_borders(bd)
        mar = tblPr.find(f"{{{W}}}tblCellMar")
        if mar is not None:
            left = mar.find(f"{{{W}}}left")
            if left is not None:
                pt = _twips_to_pt(left.get(f"{{{W}}}w"))
                if pt is not None:
                    cell_pad = pt
    return {"kind": "tbl", "rows": rows, "col_widths": col_widths,
            "borders": borders, "cell_pad_pt": cell_pad}

def _hf_blocks(part, styles_map, doc_font, doc_size, default_style_id=""):
    """header/footer part → (blocks, text_lines, images)。"""
    blocks, lines, images = [], [], []
    root = getattr(part, "element", None)
    if root is None:
        return blocks, lines, images
    for child in root.iterchildren():
        local = _local(child)
        if local == "p":
            b, text = _hf_paragraph(child, part, styles_map, doc_font, doc_size, default_style_id)
            if text.strip():
                lines.append(text.strip())
            if b["runs"] or text.strip():
                blocks.append(b)
                images.extend(r["image"] for r in b["runs"] if "image" in r)
        elif local == "tbl":
            b = _hf_table(child, part)
            if b["rows"]:
                blocks.append(b)
                for row in b["rows"]:
                    line = " ".join(c["text"] for c in row if c.get("text")).strip()
                    if line:
                        lines.append(line)
                    for c in row:
                        images.extend(r["image"] for r in c.get("runs") or [] if "image" in r)
    return blocks, lines, images

def docx_header_footer(path):
    """全文档 sectPr 顺序扫描 → {header, footer}（各自独立取首个有内容的）。

    多节文档的页眉页脚常定义在段落 pPr 里的 sectPr（第一节）而非 body 末尾，
    因此遍历所有 sectPr，default 类型优先。返回结构化 blocks 供渲染层还原
    表格/图片布局，text/images 供检索与兼容。
    """
    def _empty():
        return {"blocks": [], "text": [], "images": []}

    out = {"header": _empty(), "footer": _empty()}
    try:
        doc = Document(str(path))
        styles_map = _parse_styles(doc)
        default_pid = _default_paragraph_style(doc)
        doc_font, doc_size = _doc_defaults(doc)
        sects = list(doc.element.body.iter(f"{{{W}}}sectPr"))
        if not sects:
            return out
        for kind, ref_tag in (("header", "headerReference"), ("footer", "footerReference")):
            found = False
            for sect in sects:
                refs = sect.findall(f"{{{W}}}{ref_tag}")
                refs.sort(key=lambda r: 0 if r.get(f"{{{W}}}type") in (None, "default") else 1)
                for ref in refs:
                    rid = ref.get(f"{{{R}}}id")
                    if not rid:
                        continue
                    try:
                        part = doc.part.rels[rid].target_part
                        blocks, lines, images = _hf_blocks(part, styles_map, doc_font, doc_size, default_pid)
                    except Exception:
                        continue
                    if blocks:
                        out[kind] = {"blocks": blocks, "text": lines, "images": images}
                        found = True
                        break
                if found:
                    break
    except Exception:
        pass
    return out

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
    """w:pPr → 属性 dict（值为 pt 或原始字符串，_CLEAR 表示显式清除）。"""
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
        first = ind.get(f"{{{W}}}firstLine") or ind.get(f"{{{W}}}hanging")
        left = ind.get(f"{{{W}}}left") or ind.get(f"{{{W}}}start")
        if flc:  # 首行缩进按字：以 10.5pt/字近似（渲染端以 em 补正更准）
            out["first_line_chars"] = round(int(flc) / 100.0, 2)
        elif first:
            pt = _twips_to_pt(first)
            if pt is not None:
                out["first_line_pt"] = pt
        # 空 <w:ind/> 不覆盖继承值（Word 语义：无属性 = 未设置）
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
    pdr = ppr.find(f"{{{W}}}pBdr")
    if pdr is not None:
        borders = _parse_borders(pdr)
        if borders:
            out["borders"] = borders
    numpr = ppr.find(f"{{{W}}}numPr")
    if numpr is not None:
        out["numId"] = _attr(numpr, "numId")
        out["ilvl"] = _attr(numpr, "ilvl") or "0"
    return out

def _parse_borders(el):
    """w:pBdr / w:tblBorders / w:tcBorders → {side: css}；none/nil 忽略。"""
    sides = {"top": "top", "bottom": "bottom", "left": "left", "right": "right",
             "start": "left", "end": "right", "insideH": "insideH", "insideV": "insideV"}
    out = {}
    for tag, side in sides.items():
        e = el.find(f"{{{W}}}{tag}")
        if e is None:
            continue
        val = (e.get(f"{{{W}}}val") or "").lower()
        if val in ("", "none", "nil", "0"):
            continue
        try:
            sz_pt = max(0.5, int(e.get(f"{{{W}}}sz") or 4) / 8.0)
        except ValueError:
            sz_pt = 0.5
        color = e.get(f"{{{W}}}color") or "auto"
        color = "#000000" if color == "auto" else f"#{color}"
        out[side] = f"{sz_pt:g}pt solid {color}"
    return out


def _run_props(rpr):
    """w:rPr → 字符属性 dict（sz 为半点，转 pt）。"""
    if rpr is None:
        return {}
    out = _run_flags(rpr)
    sz = _attr(rpr, "sz") or _attr(rpr, "szCs")
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


def _default_paragraph_style(doc):
    """styles.xml 里 w:default="1" 的段落样式 id（无 pStyle 的段落继承它）。"""
    try:
        for st in doc.styles.element.findall(f"{{{W}}}style"):
            if st.get(f"{{{W}}}type") == "paragraph" and st.get(f"{{{W}}}default") == "1":
                return st.get(f"{{{W}}}styleId") or ""
    except Exception:
        pass
    return ""

def _resolve_style_chain(style_id, styles_map, max_depth=10):
    """basedOn 链上溯合并（基类先、子类覆盖）。返回 (段落属性, 字符属性)。"""
    merged_p, merged_r = {}, {}
    chain = []
    sid, depth = style_id, 0
    seen = set()
    while sid and sid in styles_map and sid not in seen and depth < max_depth:
        seen.add(sid)
        chain.append(styles_map[sid])
        sid = styles_map[sid]["basedOn"]
        depth += 1
    for entry in reversed(chain):  # 基类先写入，子类后覆盖
        for k, v in entry["p"].items():
            if v is _CLEAR:
                merged_p.pop(k, None)
            elif v is not None:
                merged_p[k] = v
        for k, v in entry["r"].items():
            if v is _CLEAR:
                merged_r.pop(k, None)
            elif v is not None:
                merged_r[k] = v
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



def _merge_para_fmt(sp, direct_p, doc_font, doc_size):
    """样式链属性 + 段落直接属性合并（_CLEAR 删除继承值，直接格式优先）。"""
    merged = dict(sp)
    for k, v in direct_p.items():
        if v is _CLEAR:
            merged.pop(k, None)
        elif v is not None:
            merged[k] = v
    merged.setdefault("font", doc_font)
    merged.setdefault("size_pt", doc_size)
    return merged

def _parse_paragraph(p, doc, index, style_names, styles_map, numbering, counter, doc_font, doc_size, default_style_id=""):
    pPr = p.find(f"{{{W}}}pPr")
    style_id = ""
    if pPr is not None:
        ps = pPr.find(f"{{{W}}}pStyle")
        if ps is not None:
            style_id = ps.get(f"{{{W}}}val") or ""
    if not style_id:
        style_id = default_style_id
    style_name = style_names.get(style_id, style_id)
    level = _heading_level(p, style_id, style_name)
    # 样式链合并：docDefaults < 样式链 < 段落直接格式
    sp, sr = _resolve_style_chain(style_id, styles_map)
    direct_p = _para_props(pPr)
    pmerged = _merge_para_fmt(sp, direct_p, doc_font, doc_size)
    # 段落标记 rPr 只影响标记本身（行高），不向 run 继承
    runs, text = _parse_runs(p, doc.part, sr)
    pb = pPr.find(f"{{{W}}}pageBreakBefore") if pPr is not None else None
    page_break_before = pb is not None and (pb.get(f"{{{W}}}val") or "true") not in ("0", "false", "none")
    page_break = False
    for br in p.iter(f"{{{W}}}br"):
        if (br.get(f"{{{W}}}type") or "") == "page":
            page_break = True
    if pPr is not None:
        sect = pPr.find(f"{{{W}}}sectPr")
        if sect is not None:
            stype = sect.find(f"{{{W}}}type")
            if stype is None or (stype.get(f"{{{W}}}val") or "nextPage") != "continuous":
                page_break = True
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
    has_image = any("image" in r for r in runs)
    if has_image and not text.strip():
        kind = "image"
    elif level:
        kind = "heading"
    else:
        kind = "paragraph"
    fmt = {k: v for k, v in pmerged.items()
           if k not in ("numId", "ilvl") and v is not None and v is not _CLEAR}
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
        "page_break": page_break,
        "page_break_before": page_break_before,
    }
    if kind == "image":
        block["image"] = next(r["image"] for r in runs if "image" in r)
    return block


def _parse_runs(p, part, base_r=None):
    """段落 → (runs, 纯文本)。part 用于解析图片关系；base_r 为继承字符属性。

    支持文本框内容（w:txbxContent）与 PAGE/NUMPAGES 域（结果文本转 {{page}}/{{pages}}）。
    """
    runs = []
    texts = []
    fields = []

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

    def field_mark(el):
        kind = el.get(f"{{{W}}}fldCharType")
        if kind == "begin":
            fields.append({"instr": "", "result": False, "emitted": False})
        elif kind == "separate" and fields:
            fields[-1]["result"] = True
        elif kind == "end" and fields:
            fields.pop()

    def emit_text(t, rpr):
        if fields and fields[-1]["result"] and not fields[-1]["emitted"]:
            fields[-1]["emitted"] = True
            tokens = fields[-1]["instr"].strip().upper().split()
            first = tokens[0] if tokens else ""
            if first == "NUMPAGES":
                add_text("{{pages}}", rpr)
                return
            if first == "PAGE":
                add_text("{{page}}", rpr)
                return
        add_text(t, rpr)

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
                    data_uri = _image_data_uri(part, blip.get(f"{{{R}}}embed"))
                    if data_uri:
                        item = {"image": data_uri}
                        ext = node.find(f".//{{{WP}}}extent")
                        if ext is not None:
                            try:
                                item["width_pt"] = round(int(ext.get("cx")) / 12700.0, 1)
                            except (TypeError, ValueError):
                                pass
                        runs.append(item)
                txbx = node.find(f".//{{{W}}}txbxContent")
                for sub in node:
                    try:
                        sq = etree.QName(sub)
                    except ValueError:
                        continue
                    if sq.namespace != W:
                        continue
                    if sq.localname == "t":
                        emit_text(sub.text or "", rpr)
                    elif sq.localname == "br":
                        add_text("\n", None)
                    elif sq.localname == "tab":
                        add_text("\t", None)
                    elif sq.localname == "fldChar":
                        field_mark(sub)
                    elif sq.localname == "instrText" and fields:
                        fields[-1]["instr"] += sub.text or ""
                if txbx is not None:
                    walk(txbx)
            elif q.localname == "fldSimple":
                fields.append({
                    "instr": node.get(f"{{{W}}}instr") or "",
                    "result": True,
                    "emitted": False,
                })
                walk(node)
                if fields:
                    fields.pop()
            elif q.localname in ("hyperlink", "smartTag", "p", "txbxContent"):
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
    return {"bold": _on("b") or _on("bCs"),
            "italic": _on("i") or _on("iCs"),
            "underline": underline}


def _image_data_uri(part, rid):
    if not rid:
        return None
    try:
        tp = part.rels[rid].target_part
        blob = tp.blob
        ct = tp.content_type or "image/png"
        return f"data:{ct};base64,{base64.b64encode(blob).decode('ascii')}"
    except Exception:
        return None


def _omml_plain_text(omath):
    return "".join(t.text or "" for t in omath.iter(f"{{{M}}}t"))


def _table_rows(tbl, part, index=0):
    """表格 → (final_rows, col_widths)；处理 gridSpan / vMerge。"""
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
            runs, text = _cell_content(tc, part)
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

    col_widths = []
    grid = tbl.find(f"{{{W}}}tblGrid")
    if grid is not None:
        for gc in grid.findall(f"{{{W}}}gridCol"):
            try:
                col_widths.append(int(gc.get(f"{{{W}}}w") or 0))
            except ValueError:
                col_widths.append(0)
    return final_rows, col_widths

def _parse_table(tbl, doc, index, style_names):
    rows, col_widths = _table_rows(tbl, doc.part, index)
    return {
        "kind": "table",
        "index": index,
        "anchor": str(index),
        "style": "",
        "level": 0,
        "text": _table_plain_text(rows),
        "runs": [],
        "rows": rows,
        "is_list": False,
        "col_widths": col_widths,
    }

def _cell_content(tc, part):
    """单元格 → (全部段落 runs，段落间以 {"text":"\\n"} 分隔， 各段落文本 join)。

    多段单元格此前只回传首段 runs，渲染层随之丢掉其余段落（简历类文档
    正文几乎全在大表格单元格里）；改为全段落拼接，空段保留空行占位。
    """
    texts = []
    runs = []
    for p in tc.findall(f"{{{W}}}p"):
        p_runs, text = _parse_runs(p, part)
        if runs:
            runs.append({"text": "\n"})
        runs.extend(p_runs)
        if text.strip():
            texts.append(text)
    return runs, "\n".join(texts)


def _table_plain_text(rows):
    lines = []
    for row in rows:
        lines.append(" | ".join(c["text"].replace("\n", " ") for c in row))
    return "\n".join(lines)
