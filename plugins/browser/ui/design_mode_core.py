# -*- coding: utf-8 -*-
"""Design Mode 纯函数层：样式白名单、矩形裁剪、prompt 组装、JS 片段。

这里不导入 Qt，便于脱离图形环境单测。控制器在 design_mode.py。
"""

import json

STYLE_KEYS = (
    "display", "position", "top", "right", "bottom", "left", "z-index",
    "float", "clear", "overflow", "overflow-x", "overflow-y",
    "width", "height", "min-width", "min-height", "max-width", "max-height",
    "margin-top", "margin-right", "margin-bottom", "margin-left",
    "padding-top", "padding-right", "padding-bottom", "padding-left",
    "border-top", "border-right", "border-bottom", "border-left",
    "border-radius", "box-shadow", "box-sizing",
    "background-color", "background-image", "background-size", "background-position",
    "color", "opacity", "visibility",
    "font-family", "font-size", "font-weight", "font-style",
    "line-height", "letter-spacing", "text-align", "text-decoration", "white-space",
    "flex-direction", "flex-wrap", "justify-content", "align-items", "align-self",
    "gap", "row-gap", "column-gap",
    "grid-template-columns", "grid-template-rows",
    "transform", "transition",
)

_NOISE_VALUES = frozenset({"none", "normal", "0px", "0"})

# 属性 -> 初始值集合。命中即丢弃，因为这些值等于没写。
_DEFAULTS = {
    "position": {"static"},
    "z-index": {"auto"},
    "overflow": {"visible"},
    "background-size": {"auto"},
    "box-sizing": {"content-box"},
    "width": {"auto"},
    "height": {"auto"},
    "min-width": {"auto"},
    "min-height": {"auto"},
    "opacity": {"1"},
    "visibility": {"visible"},
    "font-weight": {"400", "normal"},
    "font-style": {"normal"},
    "text-align": {"left", "start"},
    "background-position": {"0% 0%", "0px 0px", "0% 0% 0%"},
    "transition": {"all 0s ease 0s", "none 0s ease 0s", "all 0s"},
}

# 只在 flex / grid 布局下才有意义的属性前缀
_FLEX_ONLY = ("flex-", "align-", "justify-", "row-gap", "column-gap", "gap")
_GRID_ONLY = ("grid-",)


def clamp_rect(x, y, w, h, vw, vh, pad=40):
    """元素矩形外扩 pad 并裁剪到视口内；退化输入返回 None。"""
    left = max(0, int(x) - pad)
    top = max(0, int(y) - pad)
    right = min(int(vw), int(x + w) + pad)
    bottom = min(int(vh), int(y + h) + pad)
    if right <= left or bottom <= top:
        return None
    return left, top, right - left, bottom - top


def filter_styles(raw):
    """按白名单过滤计算样式，剔除初始值、不生效属性与重复简写。返回 [(key, value)]。"""
    display = (raw.get("display") or "").strip().lower()
    position = (raw.get("position") or "").strip().lower()
    is_flex = "flex" in display
    is_grid = "grid" in display
    overflow = (raw.get("overflow") or "").strip().lower()

    out = []
    for key in STYLE_KEYS:
        value = raw.get(key)
        if not value:
            continue
        v = value.strip().lower()
        if v in _NOISE_VALUES:
            continue
        # 未定位的元素上 top/right/bottom/left 不生效
        if key in ("top", "right", "bottom", "left") and position in ("", "static"):
            continue
        # 零边框：0px none <color> 整元素组都是废话
        if key.startswith("border-") and v.startswith("0px none"):
            continue
        # text-decoration 的 none 后面常跟颜色，前缀判定
        if key == "text-decoration" and v.startswith("none"):
            continue
        if key == "background-color" and v in ("rgba(0, 0, 0, 0)", "transparent"):
            continue
        # 布局无关的 flex/grid 属性在全掉
        if key.startswith(_GRID_ONLY) and not is_grid:
            continue
        if key.startswith(_FLEX_ONLY) and not (is_flex or is_grid):
            continue
        # overflow-x/y 与 overflow 同值时只留简写
        if key in ("overflow-x", "overflow-y") and v == overflow:
            continue
        if v in _DEFAULTS.get(key, ()):
            continue
        out.append((key, value))
    return out


def build_prompt(*, index, url, title, selector, html, styles, shot_path):
    """把一次拾取组装成可读的 Markdown 片段。"""
    parts = [f"<!-- drifox-pick {index} -->", f"页面：{url}"]
    if title:
        parts.append(f"标题：{title}")
    parts.append(f"元素：{selector}")
    if shot_path:
        parts.append(f"截图：{shot_path}")
    parts.extend(["", "```html", html or "", "```", "", "```css"])
    parts.append("; ".join(f"{k}: {v}" for k, v in styles))
    parts.extend(["```"])
    return "\n".join(parts)


_JS_PICK_TMPL = r"""
(function(x, y) {
  var el = document.elementFromPoint(x, y);
  if (!el) return null;
  var path = [];
  var cur = el;
  while (cur && cur.nodeType === 1 && cur !== document.body) {
    var seg = cur.tagName.toLowerCase();
    if (cur.id) { seg += '#' + cur.id; path.unshift(seg); break; }
    if (typeof cur.className === 'string' && cur.className.trim()) {
      seg += '.' + cur.className.trim().split(/\s+/).slice(0, 2).join('.');
    }
    var p = cur.parentElement;
    if (p) {
      var same = Array.prototype.filter.call(p.children, function(c) {
        return c.tagName === cur.tagName;
      });
      if (same.length > 1) seg += ':nth-of-type(' + (same.indexOf(cur) + 1) + ')';
    }
    path.unshift(seg);
    cur = cur.parentElement;
  }
  var cs = getComputedStyle(el);
  var keys = __KEYS__;
  var styles = {};
  for (var i = 0; i < keys.length; i++) {
    var v = cs.getPropertyValue(keys[i]);
    if (v) styles[keys[i]] = v;
  }
  var r = el.getBoundingClientRect();
  return {
    selector: path.join(' > ') || el.tagName.toLowerCase(),
    html: (el.outerHTML || '').slice(0, 4000),
    styles: styles,
    rect: {x: r.left, y: r.top, w: r.width, h: r.height},
    text: (el.innerText || '').slice(0, 200)
  };
})(__X__, __Y__)
"""

_JS_HIT_TMPL = r"""
(function(x, y) {
  var el = document.elementFromPoint(x, y);
  if (!el) return null;
  var r = el.getBoundingClientRect();
  return {
    rect: {x: r.left, y: r.top, w: r.width, h: r.height},
    tag: el.tagName.toLowerCase()
  };
})(__X__, __Y__)
"""


def _fill(tmpl, x, y, **extra):
    out = tmpl.replace("__X__", str(int(x))).replace("__Y__", str(int(y)))
    for key, value in extra.items():
        out = out.replace(f"__{key}__", value)
    return out.strip()


def js_pick(x, y):
    """返回取完整元素信息的 JS（IIFE，不依赖页面全局函数）。"""
    return _fill(_JS_PICK_TMPL, x, y, KEYS=json.dumps(list(STYLE_KEYS)))


def js_hit(x, y):
    """返回只取矩形的 JS，用于悬停高亮。"""
    return _fill(_JS_HIT_TMPL, x, y)
