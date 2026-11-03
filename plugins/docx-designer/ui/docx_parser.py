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


def parse_document(path):
    """解析 docx，返回 Block 列表（body 顺序，index 连续）。"""
    doc = Document(str(path))
    style_names = _style_name_map(doc)
    blocks = []
    body = doc.element.body
    for child in body.iterchildren():
        try:
            local = etree.QName(child).localname
        except ValueError:
            continue
        if local == "p":
            blocks.append(_parse_paragraph(child, doc, len(blocks), style_names))
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


def _parse_paragraph(p, doc, index, style_names):
    pPr = p.find(f"{{{W}}}pPr")
    style_id = ""
    if pPr is not None:
        ps = pPr.find(f"{{{W}}}pStyle")
        if ps is not None:
            style_id = ps.get(f"{{{W}}}val") or ""
    style_name = style_names.get(style_id, style_id)
    level = _heading_level(p, style_id, style_name)
    runs, text = _parse_runs(p, doc)
    is_list = _is_list(pPr, style_id, style_name)
    has_image = any("image" in r for r in runs)
    if has_image and not text.strip():
        kind = "image"
    elif level:
        kind = "heading"
    else:
        kind = "paragraph"
    block = {
        "kind": kind,
        "index": index,
        "anchor": str(index),
        "style": style_name,
        "level": level,
        "text": text,
        "runs": runs,
        "is_list": is_list,
    }
    if kind == "image":
        block["image"] = next(r["image"] for r in runs if "image" in r)
    return block


def _parse_runs(p, doc):
    """段落 → (runs, 纯文本)。遍历直接子级与 hyperlink/sdtContent，公式与图片单独成项。"""
    runs = []
    texts = []

    def add_text(t, rpr):
        if not t:
            return
        runs.append({"text": t, **_run_flags(rpr)})
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
