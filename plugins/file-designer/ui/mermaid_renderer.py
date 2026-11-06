# -*- coding: utf-8 -*-
"""Mermaid model → HTML（纯函数，无 Qt 依赖）。

优先内联 assets/mermaid.min.js 客户端渲染 SVG；库缺失或初始化失败时降级为
源码 + 提示。源码逐行列出，每行 <div data-anchor="L{n}"> 可拾取可标注。
"""

import json
from pathlib import Path

from .generic_renderer import e, wrap_html

_ASSET = Path(__file__).resolve().parent.parent / "assets" / "mermaid.min.js"

_CSS = (
    ".wrap { padding: 14px 18px 32px; } "
    ".meta { color: #d7e2f0; font-size: 13px; margin: 0 0 10px; } "
    ".diagram { background: #ffffff; border-radius: 8px; padding: 18px; "
    "overflow: auto; box-shadow: 0 2px 12px rgba(0,0,0,0.35); margin-bottom: 18px; } "
    ".diagram svg { max-width: 100%%; height: auto; } "
    ".fallback { color: #8a6d3b; background: #fffbe6; border: 1px dashed #b8860b; "
    "padding: 10px; border-radius: 6px; font-size: 13px; } "
    ".src { background: #ffffff; border-radius: 8px; padding: 8px 0; "
    "box-shadow: 0 2px 12px rgba(0,0,0,0.35); font-family: Consolas, 'Courier New', monospace; } "
    ".srow { display: flex; align-items: baseline; padding: 2px 10px; "
    "font-size: 13px; line-height: 1.55; color: #1a1a1a; white-space: pre-wrap; } "
    ".srow:hover { background: rgba(0,120,212,0.06); } "
    ".ln { flex: 0 0 46px; color: #9aa7b6; text-align: right; padding-right: 12px; "
    "user-select: none; } "
    ".warn { color: #ffd37a; margin: 8px 0 12px; font-size: 13px; } "
)

_INIT_JS = (
    "window.__mermaidReady = false;"
    "if (window.mermaid) {"
    " try { mermaid.initialize({startOnLoad:false, securityLevel:'loose', "
    "  theme:'default', flowchart:{useMaxWidth:true, htmlLabels:true}});"
    "  window.__mermaidReady = true; } catch(err){"
    "  document.getElementById('diagram').innerHTML ="
    "   '<div class=\"fallback\">Mermaid 初始化失败: ' + String(err) + '</div>'; } }"
    "else { document.getElementById('diagram').innerHTML ="
    " '<div class=\"fallback\">mermaid.min.js 未随插件安装，仅显示源码。</div>'; }"
    "if (window.__mermaidReady) {"
    " var src = window.__mermaidSrc;"
    " var el = document.getElementById('diagram');"
    " try {"
    "  var id = 'mmd-' + Date.now();"
    "  mermaid.render(id, src).then(function(res){"
    "   el.innerHTML = res.svg;"
    "   el.querySelectorAll('g.node, g.edgeLabel, .node, .edgeLabel').forEach(function(g){"
    "    var t = g.id || '';"
    "    var m = t.match(/(?:flowchart-|L-)([A-Za-z_][\\w-]*)-\\d+/);"
    "    if (m && window.__nodeLine && window.__nodeLine[m[1]])"
    "     g.setAttribute('data-anchor', window.__nodeLine[m[1]]);"
    "   });"
    "  }).catch(function(err){"
    "   el.innerHTML = '<div class=\"fallback\">Mermaid 渲染失败: ' +"
    "    String(err && err.message || err) + '</div>'; });"
    " } catch(err) {"
    "  el.innerHTML = '<div class=\"fallback\">Mermaid 渲染失败: ' + String(err) + '</div>'; } }"
)


def _read_asset():
    try:
        return _ASSET.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def render_mermaid_html(model, *, outer="#1d2533", accent="#66c6ff", restored=None):
    lines = model.get("lines") or [""]
    src = "\n".join(lines)
    src_json = json.dumps(src, ensure_ascii=False)
    lib = _read_asset()
    node_line = {
        nid: f"L{rec['first_line']}"
        for nid, rec in (model.get("nodes") or {}).items()
    }
    node_json = json.dumps(node_line, ensure_ascii=False)
    head = (
        f"<script>window.__mermaidSrc = {src_json};"
        f"window.__nodeLine = {node_json};</script>"
    )
    if lib:
        head += f"<script>{lib}</script>"

    rows = "".join(
        f'<div class="srow" data-anchor="L{i}">'
        f'<span class="ln">{i}</span><span>{e(ln) or "&nbsp;"}</span></div>'
        for i, ln in enumerate(lines, 1)
    )
    parts = [f'<div class="meta">{e(model.get("diagram_type") or "Mermaid 源码")} '
             f'· 共 {len(lines)} 行</div>']
    parts.append('<div class="diagram" id="diagram">正在渲染流程图…</div>')
    if not lib:
        parts.append('<div class="warn">assets/mermaid.min.js 缺失，已降级为源码视图</div>')
    parts.append(f'<div class="src">{rows}</div>')
    return wrap_html(
        f'<div class="wrap">{"".join(parts)}</div>',
        outer=outer, accent=accent, restored=restored,
        extra_css=_CSS, extra_js=_INIT_JS, head_html=head,
    )
