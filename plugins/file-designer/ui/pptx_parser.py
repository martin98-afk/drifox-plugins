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

_NS_P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
_NS_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_NS_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _pt(length, default=None):
    if length is None:
        return default
    try:
        return round(Emu(int(length)).pt, 2)
    except (TypeError, ValueError):
        return default


_THEME_KEYS = {
    "dark_1": "dk1", "light_1": "lt1", "dark_2": "dk2", "light_2": "lt2",
    "text_1": "dk1", "background_1": "lt1", "text_2": "dk2", "background_2": "lt2",
    "hyperlink": "hlink", "followed_hyperlink": "folHlink",
}

def _rgb(color, default=None, theme=None):
    """ColorFormat → "#rrggbb"；SCHEME 主题色查 theme 映射（拿不到原 RGB 会抛异常）。"""
    try:
        t = color.type
        if t is not None and "SCHEME" in str(t):
            key = str(color.theme_color).split(".")[-1].split(" ")[0].lower()
            key = key.replace("accent_", "accent")
            key = _THEME_KEYS.get(key, key)
            if theme and key in theme:
                return theme[key]
            return default
        rgb = color.rgb
        if rgb is None:
            return default
        return f"#{rgb}"
    except Exception:
        return default

def _theme_map(slide):
    """slide → {dk1..folHlink: "#rrggbb"}（master 关联 theme part 的 clrScheme）。"""
    try:
        from lxml import etree
        master = slide.slide_layout.slide_master
        for rel in master.part.rels.values():
            if not rel.reltype.endswith("/theme"):
                continue
            root = etree.fromstring(rel.target_part.blob)
            cs = root.find(f"{_NS_A}themeElements/{_NS_A}clrScheme")
            if cs is None:
                return {}
            out = {}
            for el in cs:
                tag = el.tag.rsplit("}", 1)[-1]
                srgb = el.find(f"{_NS_A}srgbClr")
                if srgb is not None:
                    out[tag] = f"#{srgb.get('val')}"
                else:
                    sysc = el.find(f"{_NS_A}sysClr")
                    if sysc is not None and sysc.get("lastClr"):
                        out[tag] = f"#{sysc.get('lastClr')}"
            return out
    except Exception:
        return {}

def _group_xfrm(shape):
    """group 子空间 chOff/chExt（pt）；缺失回退 off/ext。"""
    try:
        xfrm = shape.element.find(f"{_NS_P}grpSpPr/{_NS_A}xfrm")
        cho = xfrm.find(f"{_NS_A}chOff")
        che = xfrm.find(f"{_NS_A}chExt")
        return (_pt(cho.get("x"), 0.0), _pt(cho.get("y"), 0.0),
                _pt(che.get("cx"), 0.0), _pt(che.get("cy"), 0.0))
    except Exception:
        return (_pt(shape.left, 0.0), _pt(shape.top, 0.0),
                _pt(shape.width, 0.0), _pt(shape.height, 0.0))


def parse_presentation(path):
    """pptx → {w_pt, h_pt, slides:[{index, bg, bg_asset, shapes}], assets:{hash: data_uri}}。"""
    prs = Presentation(str(path))
    assets = {}
    model = {
        "w_pt": _pt(prs.slide_width, 960.0),
        "h_pt": _pt(prs.slide_height, 540.0),
        "slides": [],
        "assets": assets,
    }
    for si, slide in enumerate(prs.slides):
        shapes = []
        theme = _theme_map(slide)
        # 版式/母版非占位符形状垫底（背景图/装饰件；占位符是原型不渲染）
        _collect_layer(slide.slide_layout, slide, si, "L", assets, shapes, theme)
        if _show_master_sp(slide.slide_layout):
            _collect_layer(slide.slide_layout.slide_master, slide, si, "M", assets, shapes, theme)
        for shape in slide.shapes:
            try:
                _collect(shape, slide, si, assets, shapes, 0.0, 0.0, theme=theme)
            except Exception:
                continue
        color, bg_asset = _slide_background(slide, assets)
        model["slides"].append(
            {"index": si, "bg": color, "bg_asset": bg_asset, "shapes": shapes}
        )
    return model

def _collect_layer(layer, slide, si, prefix, assets, out, theme=None):
    for shape in layer.shapes:
        try:
            if shape.is_placeholder:
                continue
            _collect(shape, slide, si, assets, out, 0.0, 0.0, prefix, theme)
        except Exception:
            continue

def _show_master_sp(layout):
    """版式 showMasterSp="0" 时母版形状对该版式不可见。"""
    try:
        return layout._element.get("showMasterSp") != "0"
    except Exception:
        return True

def _slide_background(slide, assets):
    """背景链 slide→layout→master 首个有效填充；bgRef（主题引用）不解析。"""
    for obj in (slide, slide.slide_layout, slide.slide_layout.slide_master):
        color, asset = _part_bg(obj._element, obj.part, assets)
        if color or asset:
            return color or "#ffffff", asset
    return "#ffffff", None

def _part_bg(el, part, assets):
    bg = el.find(f"{_NS_P}cSld/{_NS_P}bg")
    if bg is None:
        return None, None
    bgPr = bg.find(f"{_NS_P}bgPr")
    if bgPr is None:
        return None, None
    blip = bgPr.find(f"{_NS_A}blipFill/{_NS_A}blip")
    if blip is not None:
        rid = blip.get(f"{_NS_R}embed")
        try:
            tp = part.rels[rid].target_part
            import base64
            import hashlib
            blob = tp.blob
            h = hashlib.md5(blob).hexdigest()[:16]
            if h not in assets:
                ct = tp.content_type or "image/png"
                assets[h] = f"data:{ct};base64," + base64.b64encode(blob).decode("ascii")
            return None, h
        except Exception:
            return None, None
    solid = bgPr.find(f"{_NS_A}solidFill/{_NS_A}srgbClr")
    if solid is not None:
        return f"#{solid.get('val')}", None
    return None, None


def _collect(shape, slide, si, assets, out, ox, oy, apfx="", theme=None, sx=1.0, sy=1.0):
    """shape → 中间结构；组合递归展平（chOff/chExt 线性换算），连接符转线段。

    (ox, oy, sx, sy)：子空间原点在页面的绝对位置与缩放；子形状坐标统一按它换算。
    """
    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        gl = _pt(shape.left, 0.0) * sx + ox
        gt = _pt(shape.top, 0.0) * sy + oy
        gw = _pt(shape.width, 0.0) * sx
        gh = _pt(shape.height, 0.0) * sy
        cx, cy, cw, chh = _group_xfrm(shape)
        nsx = (gw / cw) if cw else sx
        nsy = (gh / chh) if chh else sy
        nox = gl - cx * nsx
        noy = gt - cy * nsy
        for child in shape.shapes:
            try:
                _collect(child, slide, si, assets, out, nox, noy, apfx, theme, nsx, nsy)
            except Exception:
                continue
        return
    if shape.shape_type == MSO_SHAPE_TYPE.LINE:
        item = _line_item(shape, theme, ox, oy, sx, sy)
        if item is None:
            return
        item["anchor"] = f"{si}:{apfx}{len(out)}"
        out.append(item)
        return
    geom = _geometry(shape, slide)
    if geom is None:
        return
    left, top, width, height = geom
    base = {
        "anchor": f"{si}:{apfx}{len(out)}",
        "left": round(left * sx + ox, 2),
        "top": round(top * sy + oy, 2),
        "width": round(width * sx, 2),
        "height": round(height * sy, 2),
    }
    item = None
    if getattr(shape, "has_table", False):
        item = _table_item(shape)
    elif getattr(shape, "has_chart", False):
        item = {"kind": "unsupported", "label": "图表"}
    elif shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
        item = _image_item(shape, assets)
    elif getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
        item = _text_item(shape, slide, theme)
    else:
        item = _shape_item(shape, theme)
    if item is None:
        return
    item.update(base)
    out.append(item)

def _line_item(shape, theme, ox, oy, sx, sy):
    """连接符 → 线段；flipH/flipV 定端点，水平/垂直零宽高不经过 _geometry。"""
    try:
        left = _pt(shape.left, 0.0)
        top = _pt(shape.top, 0.0)
        width = _pt(shape.width, 0.0)
        height = _pt(shape.height, 0.0)
        xfrm = shape.element.find(f"{_NS_P}spPr/{_NS_A}xfrm")
        flip_h = xfrm is not None and xfrm.get("flipH") == "1"
        flip_v = xfrm is not None and xfrm.get("flipV") == "1"
        x1, x2 = (left + width, left) if flip_h else (left, left + width)
        y1, y2 = (top + height, top) if flip_v else (top, top + height)
        color = _rgb(shape.line.color, None, theme) or (theme or {}).get("dk1") or "#333333"
        width_pt = _pt(shape.line.width, 0.75) or 0.75
        dash = None
        try:
            d = shape.element.find(f"{_NS_P}spPr/{_NS_A}ln/{_NS_A}prstDash")
            if d is not None and d.get("val") not in (None, "solid"):
                dash = "dotted" if "dot" in d.get("val") else "dashed"
        except Exception:
            pass
        head, tail = False, False
        try:
            ln = shape.element.find(f"{_NS_P}spPr/{_NS_A}ln")
            he = ln.find(f"{_NS_A}headEnd") if ln is not None else None
            te = ln.find(f"{_NS_A}tailEnd") if ln is not None else None
            head = he is not None and he.get("type") not in (None, "none")
            tail = te is not None and te.get("type") not in (None, "none")
        except Exception:
            pass
        return {
            "kind": "line",
            "x1": round(ox + x1 * sx, 2), "y1": round(oy + y1 * sy, 2),
            "x2": round(ox + x2 * sx, 2), "y2": round(oy + y2 * sy, 2),
            "color": color, "width_pt": width_pt, "dash": dash,
            "head": head, "tail": tail,
        }
    except Exception:
        return None


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


def _placeholder_font(shape, slide, theme=None):
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
                    return (_pt(f.size), f.bold, _rgb(f.color, None, theme), f.name)
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


def _text_item(shape, slide, theme=None):
    fallback = _placeholder_font(shape, slide, theme)
    paras = []
    for p in shape.text_frame.paragraphs:
        runs = []
        pf = p.font
        p_size = _pt(pf.size) or (fallback[0] if isinstance(fallback, tuple) else fallback)
        p_bold = pf.bold if pf.bold is not None else (fallback[1] if isinstance(fallback, tuple) else None)
        p_color = _rgb(pf.color, None, theme) or (fallback[2] if isinstance(fallback, tuple) else None)
        p_font = pf.name or (fallback[3] if isinstance(fallback, tuple) else None)
        for r in p.runs:
            f = r.font
            runs.append({
                "text": r.text,
                "size_pt": _pt(f.size) or p_size,
                "bold": bool(f.bold if f.bold is not None else p_bold),
                "italic": bool(f.italic),
                "underline": bool(f.underline),
                "color": _rgb(f.color, None, theme) or p_color,
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
    item = {"kind": "text", "paras": paras, "valign": _anchor(shape.text_frame.vertical_anchor)}
    # 形状自身底色/边框：带文字的 AUTO_SHAPE 是 pptx 图形的主要形态，框信息在 fill/line
    try:
        from pptx.enum.dml import MSO_FILL
        if shape.fill.type == MSO_FILL.SOLID:
            fill = _rgb(shape.fill.fore_color, None, theme)
            if fill:
                item["fill"] = fill
    except Exception:
        pass
    try:
        line = _rgb(shape.line.color, None, theme)
        if line:
            item["line"] = line
    except Exception:
        pass
    return item


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


def _image_item(shape, assets):
    """图片 → 按 blob 哈希去重的资产引用（同一 logo 多页复用只嵌一次）。"""
    try:
        import base64
        import hashlib
        img = shape.image
        blob = img.blob
        h = hashlib.md5(blob).hexdigest()[:16]
        if h not in assets:
            ct = img.content_type or "image/png"
            assets[h] = f"data:{ct};base64," + base64.b64encode(blob).decode("ascii")
        return {"kind": "image", "asset": h}
    except Exception:
        return None


def _table_item(shape):
    table = shape.table
    col_widths = [_pt(c.width, 0.0) for c in table.columns]
    rows = []
    for row in table.rows:
        cells = []
        for cell in row.cells:
            if getattr(cell, "is_spanned", False):
                continue  # 被合并覆盖的格子不输出，由 origin 的 colspan/rowspan 占位
            c = {"text": cell.text}
            if getattr(cell, "is_merge_origin", False):
                if cell.span_height > 1:
                    c["rowspan"] = cell.span_height
                if cell.span_width > 1:
                    c["colspan"] = cell.span_width
            cells.append(c)
        rows.append(cells)
    return {"kind": "table", "rows": rows, "col_widths": col_widths,
            "row_height_pt": _pt(table.rows[0].height) if len(table.rows) else None}


def _shape_item(shape, theme=None):
    fill = None
    line = None
    try:
        from pptx.enum.dml import MSO_FILL
        if shape.fill.type == MSO_FILL.SOLID:
            fill = _rgb(shape.fill.fore_color, None, theme)
    except Exception:
        pass
    try:
        line = _rgb(shape.line.color, None, theme)
    except Exception:
        pass
    if not fill and not line:
        return None
    return {"kind": "shape", "fill": fill, "line": line}
