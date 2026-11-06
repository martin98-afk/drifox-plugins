# -*- coding: utf-8 -*-
"""Mermaid 源码解析（纯函数，无 Qt 依赖）。

不做完整 AST：按行建索引，识别图类型与节点/连线文本，支持点节点反查首次出现行。
锚点 L{行号}（1 起）。

model：
  {"mode": "mermaid", "source": 绝对路径, "diagram_type", "lines": [str],
   "nodes": {node_id: {"first_line", "text"}}, "lookup": callable}
lookup("L3") -> {"mode","kind":"mermaid_line","text","diagram_type","context","anchor"}
"""

import re
from pathlib import Path

_DIAGRAM_RE = re.compile(
    r"^\s*(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|"
    r"erDiagram|gantt|pie|journey|gitGraph|mindmap|timeline|quadrantChart|"
    r"requirementDiagram|C4Context|sankey|xychart)\b",
    re.IGNORECASE,
)
_NODE_RE = re.compile(r"(?:^|[\s(\[>|;-])([A-Za-z_][\w-]*)\s*(?:\[\(?\[?|\(\(?|\{\{?|>)")
def _diagram_type(lines):
    for ln in lines:
        m = _DIAGRAM_RE.match(ln)
        if m:
            return ln.strip()
    return ""


def _node_ids(lines):
    out = {}
    for i, ln in enumerate(lines, 1):
        stripped = ln.strip()
        if not stripped or stripped.startswith("%%"):
            continue
        for m in _NODE_RE.finditer(ln):
            nid = m.group(1)
            if nid.lower() in ("graph", "flowchart", "subgraph", "end", "class", "style", "click"):
                continue
            out.setdefault(nid, {"first_line": i, "text": stripped})
    return out


def _context(lines, line_no, radius=2):
    lo = max(1, line_no - radius)
    hi = min(len(lines), line_no + radius)
    return "\n".join(f"{n:>3} | {lines[n - 1]}" for n in range(lo, hi + 1))


def parse_mermaid(path):
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    raw = None
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            raw = p.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if raw is None:
        raise ValueError("Mermaid 源码编码无法识别")
    lines = raw.splitlines() or [""]
    diagram_type = _diagram_type(lines)
    nodes = _node_ids(lines)
    index = {}
    for i, ln in enumerate(lines, 1):
        index[f"L{i}"] = {
            "mode": "mermaid", "kind": "mermaid_line", "anchor": f"L{i}",
            "text": ln.rstrip(), "diagram_type": diagram_type,
            "context": _context(lines, i),
        }

    def lookup(anchor):
        if isinstance(anchor, str) and anchor in index:
            return index[anchor]
        # 点节点反查：anchor 可能是 SVG 里 data-anchor="node:A"
        if isinstance(anchor, str) and anchor.startswith("node:"):
            nid = anchor[5:]
            rec = nodes.get(nid)
            if rec:
                return index.get(f"L{rec['first_line']}")
        return None

    return {
        "mode": "mermaid", "source": str(p), "diagram_type": diagram_type,
        "lines": lines, "nodes": nodes, "lookup": lookup,
    }


def anchor_for_node(model, node_id):
    """节点 id → 锚点（供 renderer 给 SVG 节点挂 data-anchor）。"""
    rec = model.get("nodes", {}).get(node_id)
    return f"L{rec['first_line']}" if rec else None
