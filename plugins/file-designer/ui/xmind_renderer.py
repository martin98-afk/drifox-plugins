# -*- coding: utf-8 -*-
"""XMind model → 自绘 SVG HTML（纯函数，无 Qt 依赖）。

根居中、一级分支左右交替、贝塞尔连线；每个节点 <g data-anchor> 可拾取可标注。
不还原原文件配色与自由布局，按深度给统一色阶。
"""

from .generic_renderer import e, wrap_html

_PAD = 40
_NODE_W_BASE = 96
_NODE_H = 34
_GAP_X = 190
_GAP_Y = 16
_MAX_DEPTH = 6
_DEPTH_COLORS = [
    ("#2b6cb0", "#ffffff"), ("#3182ce", "#ffffff"), ("#4299e1", "#ffffff"),
    ("#63b3ed", "#1a1a1a"), ("#90cdf4", "#1a1a1a"), ("#bee3f8", "#1a1a1a"),
    ("#e2e8f0", "#1a1a1a"),
]


def _char_width(ch):
    return 12.0 if ord(ch) > 0x2E80 else 7.2


def _wrap_lines(text, max_chars=28, max_lines=3):
    """按显示宽度折行（中文 12px / 英文 7.2px，基准 14px 字号）。"""
    lines, cur, width = [], "", 0.0
    for ch in str(text or ""):
        cw = _char_width(ch)
        if width + cw > max_chars * 8.4 and cur:
            lines.append(cur)
            cur, width = ch, cw
        else:
            cur += ch
            width += cw
        if len(lines) >= max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if not lines:
        lines = ["（未命名主题）"]
    consumed = sum(len(x) for x in lines)
    if consumed < len(str(text or "")) and lines:
        lines[-1] = lines[-1][:-1] + "…"
    return lines


def _node_w(node):
    lines = _wrap_lines(node["title"])
    longest = max(sum(_char_width(c) for c in ln) for ln in lines)
    return max(_NODE_W_BASE, min(260, int(longest + 24)))


def _node_h(node):
    return max(_NODE_H, 16 + 17 * len(_wrap_lines(node["title"])))


def _subtree_height(node, depth=0):
    if depth > _MAX_DEPTH or not node.get("children"):
        return _node_h(node)
    kids = sum(_subtree_height(c, depth + 1) + _GAP_Y for c in node["children"]) - _GAP_Y
    return max(_node_h(node), kids)


def _layout(node, x, cy, depth, side, out, edges):
    """递归布局；返回本节点中心的 y。side=1 向右展开，side=-1 向左。"""
    h = _node_h(node)
    w = _node_w(node)
    out.append((node, x, cy, w, h, depth))
    kids = node.get("children") or []
    if not kids or depth >= _MAX_DEPTH:
        return cy
    total = sum(_subtree_height(c, depth + 1) + _GAP_Y for c in kids) - _GAP_Y
    cursor = cy - total / 2.0
    child_x = x + side * (_GAP_X + w / 2.0)
    for c in kids:
        sh = _subtree_height(c, depth + 1)
        child_cy = _layout(c, child_x, cursor + sh / 2.0, depth + 1, side if depth > 0 else side, out, edges)
        edges.append((x + side * w / 2.0, cy, child_x - side * _node_w(c) / 2.0, child_cy, depth + 1))
        cursor += sh + _GAP_Y
    return cy


def _render_node(node, x, cy, w, h, depth):
    fill, ink = _DEPTH_COLORS[min(depth, len(_DEPTH_COLORS) - 1)]
    lines = _wrap_lines(node["title"])
    lh = 17
    top = cy - (len(lines) - 1) * lh / 2.0 + 5
    tspans = "".join(
        f'<tspan x="{x:.1f}" y="{top + i * lh:.1f}" text-anchor="middle">{e(ln)}</tspan>'
        for i, ln in enumerate(lines)
    )
    tip = node["title"]
    if node.get("note"):
        tip += " ｜ 备注: " + node["note"]
    if node.get("labels"):
        tip += " ｜ 标签: " + ", ".join(node["labels"])
    return (
        f'<g data-anchor="{e(node["anchor"])}" class="mnode">'
        f'<title>{e(tip)}</title>'
        f'<rect x="{x - w / 2:.1f}" y="{cy - h / 2:.1f}" width="{w}" height="{h}" '
        f'rx="8" fill="{fill}" stroke="rgba(0,0,0,0.25)" stroke-width="1"/>'
        f'<text fill="{ink}" font-size="14" font-family="Microsoft YaHei, sans-serif">{tspans}</text>'
        f"</g>"
    )


def _render_sheet_svg(sheet):
    root = sheet["root"]
    out, edges = [], []
    kids = root.get("children") or []
    right = kids[0::2]
    left = kids[1::2]
    # 根固定 (0,0)，一级分左右，各自纵向排布
    root_w = _node_w(root)
    out.append((root, 0.0, 0.0, root_w, _node_h(root), 0))
    for group, side in ((right, 1), (left, -1)):
        if not group:
            continue
        total = sum(_subtree_height(c, 1) + _GAP_Y for c in group) - _GAP_Y
        cursor = -total / 2.0
        x0 = side * (_GAP_X + root_w / 2.0)
        for c in group:
            sh = _subtree_height(c, 1)
            cy = _layout(c, x0, cursor + sh / 2.0, 1, side, out, edges)
            edges.append((side * root_w / 2.0, 0.0, x0 - side * _node_w(c) / 2.0, cy, 1))
            cursor += sh + _GAP_Y
    xs = [x - w / 2 - _PAD for _, x, _, w, _, _ in out] + [x + w / 2 + _PAD for _, x, _, w, _, _ in out]
    ys = [cy - h / 2 - _PAD for _, _, cy, _, h, _ in out] + [cy + h / 2 + _PAD for _, _, cy, _, h, _ in out]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    vb = f"{min_x:.1f} {min_y:.1f} {max_x - min_x:.1f} {max_y - min_y:.1f}"
    edge_html = "".join(
        f'<path d="M {x1:.1f} {y1:.1f} C {(x1 + x2) / 2:.1f} {y1:.1f}, '
        f'{(x1 + x2) / 2:.1f} {y2:.1f}, {x2:.1f} {y2:.1f}" '
        f'fill="none" stroke="rgba(120,140,170,0.75)" stroke-width="{3 if d <= 1 else 2}"/>'
        for x1, y1, x2, y2, d in edges
    )
    node_html = "".join(_render_node(*item) for item in out)
    return (
        f'<svg class="mind" viewBox="{vb}" width="{max_x - min_x:.0f}" '
        f'height="{max_y - min_y:.0f}" xmlns="http://www.w3.org/2000/svg">'
        f"{edge_html}{node_html}</svg>"
    )


_CSS = (
    ".wrap { padding: 16px 20px 30px; } "
    ".sheet-title { color: #d7e2f0; font-size: 15px; margin: 4px 0 12px; "
    "padding-left: 8px; border-left: 3px solid var(--accent); } "
    ".sheet-box { background: #ffffff; border-radius: 8px; margin-bottom: 20px; "
    "padding: 14px; overflow: auto; box-shadow: 0 2px 12px rgba(0,0,0,0.35); } "
    "svg.mind { display: block; margin: 0 auto; } "
    ".mnode[data-anchor] { cursor: pointer; } "
    ".mnode text { pointer-events: none; user-select: none; } "
    ".warn { color: #ffd37a; margin: 8px 0 14px; font-size: 13px; } "
)


def render_xmind_html(model, *, outer="#1d2533", accent="#66c6ff", restored=None):
    parts = []
    if model.get("truncated"):
        parts.append(f'<div class="warn">节点数超过上限已截断（最多 {800} 个）</div>')
    for i, sh in enumerate(model.get("sheets") or []):
        parts.append(f'<div class="sheet-title">工作表 {i + 1}：{e(sh.get("name"))}</div>')
        parts.append(f'<div class="sheet-box">{_render_sheet_svg(sh)}</div>')
    return wrap_html(
        f'<div class="wrap">{"".join(parts)}</div>',
        outer=outer, accent=accent, restored=restored, extra_css=_CSS,
    )
