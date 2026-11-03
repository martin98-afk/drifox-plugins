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

_NOISE_VALUES = frozenset({"none", "normal", "auto", "0px", "0", "rgba(0, 0, 0, 0)"})


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
    """按白名单过滤计算样式，剔除空值与噪音默认值。返回 [(key, value)]。"""
    out = []
    for key in STYLE_KEYS:
        value = raw.get(key)
        if not value:
            continue
        if value.strip().lower() in _NOISE_VALUES:
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
