# -*- coding: utf-8 -*-
"""pptx 解析：Presentation → 固定画布中间结构（无 Qt 依赖）。

坐标一律 pt；锚点 "slideIdx:shapeIdx"（shape 按 spTree 顺序，含组合内元素展平）。
已知简化：主题色/渐变只取纯色，图表/媒体降级占位，母版版式只用于占位符几何与字号回退。
"""

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Emu, Pt

_DEFAULT_PT = 18.0
_TITLE_PT = 44.0
_SUBTITLE_PT = 32.0


def _pt(length, default=None):
    if length is None:
        return default
    try:
        return round(Emu(int(length)).pt, 2)
    except (TypeError, ValueError):
        return default


def _rgb(color, default=None):
    try:
        rgb = color.rgb
        if rgb is None:
            return default
        return f"#{rgb}"
    except Exception:
        return default


def parse_presentation(path):
    """pptx → {w_pt, h_pt, slides:[{index, bg, shapes}]}。"""
    prs = Presentation(str(path))
    model = {
        "w_pt": _pt(prs.slide_width, 960.0),
        "h_pt": _pt(prs.slide_height, 540.0),
        "slides": [],
    }
    for si, slide in enumerate(prs.slides):
        shapes = []
        for shape in slide.shapes:
            try:
                _collect(shape, slide, si, shapes, 0.0, 0.0)
            except Exception:
                continue
        model["slides"].append({"index": si, "bg": _slide_bg(slide), "shapes": shapes})
    return model


def _collect(shape, slide, si, out, ox, oy):
    """shape → 中间结构；组合递归展平（子坐标加偏移）。"""
    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        gl = _pt(shape.left, 0.0)
        gt = _pt(shape.top, 0.0)
        for child in shape.shapes:
            _collect(child, slide, si, out, ox + gl, oy + gt)
        return
    geom = _geometry(shape, slide)
    if geom is None:
        return
    left, top, width, height = geom
    base = {
        "anchor": f"{si}:{len(out)}",
        "left": round(left + ox, 2),
        "top": round(top + oy, 2),
        "width": width,
        "height": height,
    }
    item = None
    if getattr(shape, "has_table", False):
        item = _table_item(shape)
    elif getattr(shape, "has_chart", False):
        item = {"kind": "unsupported", "label": "图表"}
    elif shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
        item = _image_item(shape)
    elif getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
        item = _text_item(shape, slide)
    else:
        item = _shape_item(shape)
    if item is None:
        return
    item.update(base)
    out.append(item)


def _geometry(shape, slide):
    left = _pt(shape.left)
    top = _pt(shape.top)
    width = _pt(shape.width)
    height = _pt(shape.height)
    if shape.is_placeholder:
        idx = shape.placeholder_format.idx
        for src in (slide.slide_layout, slide.slide_layout.slide_master):
            for ph in src.placeholders:
                if ph.placeholder_format.idx != idx:
                    continue
                left = left if left is not None else _pt(ph.left)
                top = top if top is not None else _pt(ph.top)
                width = width if width is not None else _pt(ph.width)
                height = height if height is not None else _pt(ph.height)
                break
            if None not in (left, top, width, height):
                break
    if None in (left, top, width, height) or width <= 0 or height <= 0:
        return None
    return left, top, width, height


def _placeholder_font(shape, slide):
    """占位符 → (size_pt, bold, color, font_name) 的最佳回退。"""
    if not shape.is_placeholder:
        return None
    idx = shape.placeholder_format.idx
    for src in (slide.slide_layout, slide.slide_layout.slide_master):
        for ph in src.placeholders:
            if ph.placeholder_format.idx != idx or not ph.has_text_frame:
                continue
            for p in ph.text_frame.paragraphs:
                f = p.font
                if f.size is not None:
                    return (_pt(f.size), f.bold, _rgb(f.color), f.name)
                for r in p.runs:
                    if r.font.size is not None:
                        return (_pt(r.font.size), r.font.bold, _rgb(r.font.color), r.font.name)
    try:
        ptype = str(shape.placeholder_format.type)
    except Exception:
        ptype = ""
    if "TITLE" in ptype:
        return _SUBTITLE_PT if "CENTER" not in ptype else _TITLE_PT
    if "SUBTITLE" in ptype:
        return _SUBTITLE_PT
    return _DEFAULT_PT


def _text_item(shape, slide):
    fallback = _placeholder_font(shape, slide)
    paras = []
    for p in shape.text_frame.paragraphs:
        runs = []
        pf = p.font
        p_size = _pt(pf.size) or (fallback[0] if isinstance(fallback, tuple) else fallback)
        p_bold = pf.bold if pf.bold is not None else (fallback[1] if isinstance(fallback, tuple) else None)
        p_color = _rgb(pf.color) or (fallback[2] if isinstance(fallback, tuple) else None)
        p_font = pf.name or (fallback[3] if isinstance(fallback, tuple) else None)
        for r in p.runs:
            f = r.font
            runs.append({
                "text": r.text,
                "size_pt": _pt(f.size) or p_size,
                "bold": bool(f.bold if f.bold is not None else p_bold),
                "italic": bool(f.italic),
                "underline": bool(f.underline),
                "color": _rgb(f.color) or p_color,
                "font": f.name or p_font,
            })
        if not runs and p.text:
            runs.append({"text": p.text, "size_pt": p_size, "bold": bool(p_bold),
                         "italic": False, "underline": False, "color": p_color, "font": p_font})
        line = p.line_spacing
        line_val, line_pt = None, None
        if isinstance(line, float):
            line_val = round(line, 2)
        elif line is not None:
            line_pt = _pt(line)
        paras.append({
            "align": _align(p.alignment),
            "level": p.level or 0,
            "space_before_pt": _pt(p.space_before),
            "space_after_pt": _pt(p.space_after),
            "line": line_val,
            "line_pt": line_pt,
            "runs": runs,
        })
    return {"kind": "text", "paras": paras, "valign": _anchor(shape.text_frame.vertical_anchor)}


def _anchor(value):
    if value is None:
        return "top"
    s = str(value).upper()
    if "MIDDLE" in s:
        return "middle"
    if "BOTTOM" in s:
        return "bottom"
    return "top"


def _align(value):
    if value is None:
        return None
    s = str(value).upper()
    if "CENTER" in s:
        return "center"
    if "RIGHT" in s:
        return "right"
    if "JUSTIFY" in s or "DISTRIBUTE" in s:
        return "justify"
    if "LEFT" in s:
        return "left"
    return None


def _image_item(shape):
    try:
        img = shape.image
        return {
            "kind": "image",
            "src": f"data:{img.content_type or 'image/png'};base64,"
                   + __import__("base64").b64encode(img.blob).decode("ascii"),
        }
    except Exception:
        return None


def _table_item(shape):
    table = shape.table
    col_widths = [_pt(c.width, 0.0) for c in table.columns]
    rows = []
    for row in table.rows:
        cells = []
        for cell in row.cells:
            cells.append({"text": cell.text})
        rows.append(cells)
    return {"kind": "table", "rows": rows, "col_widths": col_widths,
            "row_height_pt": _pt(table.rows[0].height) if len(table.rows) else None}


def _shape_item(shape):
    fill = None
    line = None
    try:
        from pptx.enum.dml import MSO_FILL
        if shape.fill.type == MSO_FILL.SOLID:
            fill = _rgb(shape.fill.fore_color)
    except Exception:
        pass
    try:
        line = _rgb(shape.line.color)
    except Exception:
        pass
    if not fill and not line:
        return None
    return {"kind": "shape", "fill": fill, "line": line}


def _slide_bg(slide):
    try:
        from pptx.enum.dml import MSO_FILL
        fill = slide.background.fill
        if fill.type == MSO_FILL.SOLID:
            return _rgb(fill.fore_color, "#ffffff")
    except Exception:
        pass
    return "#ffffff"
