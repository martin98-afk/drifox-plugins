# -*- coding: utf-8 -*-
"""通用格式 HTML 骨架（纯函数，无 Qt 依赖）。

所有新格式 renderer 共用：qrc qwebchannel.js + _BOOT_JS/_ANNOTATE_JS/_PICK_JS
+ window.__restored + note-box DOM + 拾取/标注 hover 样式。
"""

import json
from html import escape

from .html_renderer import _ANNOTATE_JS, _BOOT_JS, _PICK_JS

_BASE_CSS = (
    ":root { --accent: %(accent)s; } "
    "* { box-sizing: border-box; } "
    "html, body { margin: 0; padding: 0; } "
    "body { background: %(outer)s; color: #1a1a1a; "
    "font-family: 'Microsoft YaHei', sans-serif; font-size: 14px; } "
    "body.pick [data-anchor] { cursor: crosshair; } "
    "body.pick [data-anchor]:hover { outline: 2px solid var(--accent); outline-offset: 1px; } "
    "body.annotate [data-anchor] { cursor: text; } "
    "body.annotate [data-anchor]:hover { outline: 2px dashed #e6a23c; outline-offset: 1px; } "
    "[data-anchor].annotated { outline: 2px solid rgba(230,162,60,0.55); } "
    ".amark { display: inline-block; min-width: 1.3em; margin-right: 0.3em; "
    "padding: 0 0.25em; border-radius: 3px; background: #e6a23c; color: #fff; "
    "font-size: 0.72em; text-align: center; font-weight: bold; vertical-align: 0.25em; } "
    "#note-box { position: absolute; z-index: 99; background: #fffbe6; border: 1px solid #e6a23c; "
    "border-radius: 6px; padding: 8px; box-shadow: 0 3px 10px rgba(0,0,0,0.3); width: 280px; } "
    "#note-box textarea { width: 100%%; height: 54px; box-sizing: border-box; border: 1px solid #d9d9d9; "
    "border-radius: 4px; font-size: 12px; padding: 4px; resize: vertical; } "
    "#note-box .nbtns { margin-top: 6px; text-align: right; } "
    "#note-box button { border: 1px solid #d9d9d9; background: #fff; border-radius: 4px; "
    "padding: 2px 10px; margin-left: 6px; cursor: pointer; } "
    "#note-box button.primary { background: #e6a23c; color: #fff; border-color: #e6a23c; } "
    "#note-box button.danger { background: #d9534f; color: #fff; border-color: #d9534f; display: none; } "
)

_NOTE_BOX = (
    '<div id="note-box" style="display:none">'
    '<textarea placeholder="输入对选中元素的注释…"></textarea>'
    '<div class="nbtns"><button class="danger" onclick="window.__deleteNote()">删除</button>'
    '<button onclick="window.__closeNote(false)">取消</button>'
    '<button class="primary" onclick="window.__closeNote(true)">保存注释</button></div></div>'
)


def wrap_html(body_html, *, outer="#1d2533", accent="#66c6ff", restored=None,
              extra_css="", extra_js="", head_html=""):
    """拼装完整 HTML。extra_css / extra_js / head_html 原样写入，百分号无需转义。

    head_html 插在 _BOOT_JS 之后（保证 window.onerror 先注册），用于内联大体积库。
    """
    css = _BASE_CSS % {"accent": accent, "outer": outer} + extra_css
    restored_json = json.dumps(restored or [], ensure_ascii=False)
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f"<style>{css}</style>"
        '<script src="qrc:///qtwebchannel/qwebchannel.js"></script>'
        f"<script>{_BOOT_JS}</script>"
        f"{head_html}"
        f"<script>window.__restored = {restored_json};</script>"
        "</head><body>"
        f"{body_html}"
        f"{_NOTE_BOX}"
        f"<script>{extra_js}</script>"
        f"<script>{_ANNOTATE_JS}</script>"
        f"<script>{_PICK_JS}</script></body></html>"
    )


def e(s):
    return escape(str(s if s is not None else ""), quote=True)
