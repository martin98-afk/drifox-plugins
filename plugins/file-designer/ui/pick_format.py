# -*- coding: utf-8 -*-
"""拾取回填文本格式化（纯函数，无 Qt 依赖，可单测）。

设计目标：让模型不靠截图也能定位元素——
- 文件给绝对路径（模型可直接用工具打开）
- 表格给全表结构化文本（列以 " | " 分隔，行以换行分隔）
- 单元格给「格文本 + 所在行 + 表格全文」三层上下文
- 段落给全文（超长截断），不再用 200 字预览
- 首次回填附锚点语义说明（#N = body 第 N 个块）
- pptx 锚点为 `幻灯片:元素`（0 起）
- 新格式锚点：xmind `s{sheet}/n/{路径}`、xlsx `s{sheet}!B3`、
  csv `r{行}c{列}`、mermaid `L{行号}`
"""

_TEXT_CAP = 1200      # 单块文本上限
_TABLE_CAP = 3000     # 全表文本上限

_MODE_LABEL = {
    "docx": "docx", "pptx": "pptx", "xmind": "xmind",
    "xlsx": "excel", "csv": "csv", "mermaid": "mermaid",
}

_GUIDE = {
    "docx": "#N = 文档 body 第 N 个块,从 0 数起;表格单元格 N:r行c列;header/footer = 页眉/页脚",
    "pptx": "pptx 为 幻灯片:元素（0 起）",
    "xmind": "xmind 为 s工作表序号/n/节点路径（0 为根,后续为 children 序号）,如 s0/n/0.2.1",
    "xlsx": "excel 为 s工作表序号!列字母行号,如 s1!B3（工作表 0 起,行列 1 起）",
    "csv": "csv 为 r行c列（均 0 起,第 0 行是表头）;table = 整表",
    "mermaid": "mermaid 为 L行号（1 起）,指向 .mmd 源码对应行",
}

def _row_text(row):
    return " | ".join(
        (c.get("text") or "").replace("\n", " ").strip() for c in row
    )

def format_table_text(rows, cap=_TABLE_CAP):
    lines = [_row_text(row) for row in (rows or [])]
    text = "\n".join(lines)
    if len(text) > cap:
        text = text[:cap] + "…(截断)"
    return text

def _cell_info(block, anchor):
    """单元格锚点 → (格文本, 所在行文本)。找不到返回 (None, None)。"""
    try:
        r_part, _c_part = anchor.split(":", 1)[1].split("c", 1)
        r_i = int(r_part[1:])
    except (ValueError, IndexError):
        return None, None
    rows = block.get("rows") or []
    if r_i >= len(rows):
        return None, None
    row = rows[r_i]
    cell_text = None
    for c in row:
        if c.get("anchor") == anchor:
            cell_text = (c.get("text") or "").strip()
            break
    return cell_text, _row_text(row)

_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

def _circled(n):
    return _CIRCLED[n - 1] if 1 <= n <= 20 else f"({n})"

def _mode_of(path_display, block):
    if block and block.get("mode"):
        return block["mode"]
    low = str(path_display).lower()
    for suffix, mode in (
        (".pptx", "pptx"), (".xmind", "xmind"), (".xlsx", "xlsx"),
        (".xlsm", "xlsx"), (".csv", "csv"), (".mmd", "mermaid"),
        (".mermaid", "mermaid"), (".docx", "docx"),
    ):
        if low.endswith(suffix):
            return mode
    return "docx"

def _pptx_desc(anchor):
    try:
        page, idx = anchor.split(":", 1)
        return f"[幻灯片 {int(page) + 1} 元素 {int(idx) + 1}]"
    except (ValueError, TypeError):
        return f"[元素 #{anchor}]"

def _desc_for(mode, anchor, block=None):
    if mode == "pptx":
        return _pptx_desc(anchor)
    if mode == "docx":
        if anchor == "header":
            return "[页眉]"
        if anchor == "footer":
            return "[页脚]"
        if ":r" in anchor:
            base, cell = anchor.split(":", 1)
            return f"[表格 #{base} 单元格 {cell}]"
        kind = (block or {}).get("kind")
        if kind == "table":
            return f"[表格 #{anchor}]"
        if kind == "image":
            return f"[图片 #{anchor}]"
        if kind:
            return f"[{kind} #{anchor} | {(block or {}).get('style') or kind}]"
        return f"[元素 #{anchor}]"
    if mode == "xmind":
        return f"[节点 {anchor}]"
    if mode == "xlsx":
        return f"[单元格 {anchor}]"
    if mode == "csv":
        return f"[整表]" if anchor == "table" else f"[单元格 {anchor}]"
    if mode == "mermaid":
        return f"[源码 {anchor}]"
    return f"[元素 #{anchor}]"

def normalize_annotations(annotations):
    """旧条目 {anchor: x} → {anchors: [x]}；返回新列表，不修改输入。"""
    out = []
    for a in annotations or []:
        item = dict(a or {})
        anchors = item.get("anchors")
        if not isinstance(anchors, list) or not anchors:
            old = item.pop("anchor", None)
            anchors = [old] if old else ["?"]
        item["anchors"] = list(anchors)
        item.pop("anchor", None)
        out.append(item)
    return out

def _anchors_desc(mode, anchors):
    descs = [_desc_for(mode, a) for a in anchors]
    if len(descs) > 3:
        return "、".join(descs[:3]) + f" 等 {len(descs)} 处"
    return "、".join(descs)

def format_annotations(path_display, annotations, mode=None):
    """标注统一发送文本：模型逐条按注释修改。组合条目一条注释挂多个锚点。"""
    mode = mode or _mode_of(path_display, None)
    label = _MODE_LABEL.get(mode, mode)
    annotations = normalize_annotations(annotations)
    lines = [f"📝 {label} 标注 共 {len(annotations)} 条 [{path_display}]"]
    for a in annotations:
        lines.append(
            f"{_circled(int(a.get('seq') or 0))}"
            f"{_anchors_desc(mode, a.get('anchors') or ['?'])} "
            f"\"{(a.get('snippet') or '').strip()}\"")
        lines.append(f"  ↳ 注释：{a.get('comment') or ''}")
        if a.get("shot"):
            lines.append(f"  截图：{a['shot']}")
    lines.append(f"（锚点规则: {_GUIDE.get(mode, '见元素描述')};请逐条按注释修改对应元素）")
    return "\n".join(lines)

def format_batch_pick(start_count, path_display, items, blocks_by_anchor,
                      shot_path, mode, first_guide=False):
    """框选批量拾取文本：逐元素 format_pick 连号拼接，截图仅首条携带。"""
    texts = []
    for i, it in enumerate(items):
        texts.append(format_pick(
            start_count + i, path_display, it.get("anchor", "?"),
            blocks_by_anchor.get(it.get("anchor")),
            it.get("preview") or "",
            shot_path if i == 0 else None,
            include_guide=bool(first_guide and i == 0),
            mode=mode,
        ))
    return "\n".join(texts)

def _generic_block_lines(mode, block, preview):
    """新格式 lookup 结构 → 回填正文行。"""
    lines = []
    kind = block.get("kind") or ""
    if kind == "xmind_node":
        path = block.get("path") or []
        if path:
            lines.append("层级: " + " → ".join(str(x) for x in path))
        if block.get("siblings"):
            lines.append("同级: " + " | ".join(str(x) for x in block["siblings"]))
        if block.get("text"):
            lines.append(f'"{block["text"]}"')
        if block.get("note"):
            lines.append(f"备注: {block['note']}")
    elif kind == "sheet_cell":
        if block.get("sheet"):
            lines.append(f"工作表: {block['sheet']}")
        if block.get("header") is not None:
            lines.append(f"表头: {block['header']}")
        if block.get("text"):
            lines.append(f'"{block["text"]}"')
        if block.get("row_text"):
            lines.append(f"所在行: {block['row_text']}")
    elif kind == "sheet_table":
        rows = block.get("rows") or []
        full = format_table_text(rows)
        if full:
            lines.append(f"表格全文:\n{full}")
    elif kind == "mermaid_line":
        if block.get("diagram_type"):
            lines.append(f"图类型: {block['diagram_type']}")
        if block.get("text"):
            lines.append(f'"{block["text"]}"')
        if block.get("context"):
            lines.append(f"上下文:\n{block['context']}")
    elif block.get("text"):
        lines.append(f'"{block["text"]}"')
    if not lines and preview:
        lines.append(f'"{preview}"')
    return lines

def format_pick(count, path_display, anchor, block, preview, shot_path, *,
                include_guide=False, mode=None):
    """组装回填文本。anchor 含 ":r" 即表格单元格。"""
    mode = mode or _mode_of(path_display, block)
    label = _MODE_LABEL.get(mode, mode)
    lines = [f"📎 {label} 拾取 #{count} [{path_display}]", _desc_for(mode, anchor, block)]
    if block and block.get("mode") and block["mode"] not in ("docx", "pptx"):
        lines.extend(_generic_block_lines(mode, block, preview))
    elif mode in ("xmind", "xlsx", "csv", "mermaid") and block:
        lines.extend(_generic_block_lines(mode, block, preview))
    elif mode == "pptx":
        if block is not None and block.get("kind") == "table":
            full = format_table_text(block.get("rows") or [])
            lines.append(full if full else f'"{preview}"')
        elif block is not None:
            text = (block.get("text") or "").strip()
            if len(text) > _TEXT_CAP:
                text = text[:_TEXT_CAP] + "…(截断)"
            lines.append(f'"{text}"' if text else f'"{preview}"')
        elif preview:
            lines.append(f'"{preview}"')
    elif anchor == "header" or anchor == "footer":
        if preview:
            lines.append(f'"{preview}"')
    elif ":r" in anchor:
        if block is not None and block.get("kind") == "table":
            cell_text, row_text = _cell_info(block, anchor)
            if cell_text:
                lines.append(f'"{cell_text}"')
            if row_text:
                lines.append(f"所在行: {row_text}")
            full = format_table_text(block.get("rows") or [])
            if full:
                lines.append(f"表格全文:\n{full}")
        elif preview:
            lines.append(f'"{preview}"')
    elif block is not None and block.get("kind") == "table":
        full = format_table_text(block.get("rows") or [])
        lines.append(full if full else f'"{preview}"')
    elif block is not None and block.get("kind") == "image":
        pass
    elif block is not None:
        style = block.get("style") or block.get("kind", "?")
        text = (block.get("text") or "").strip()
        if len(text) > _TEXT_CAP:
            text = text[:_TEXT_CAP] + "…(截断)"
        lines.append(f"[{block.get('kind', '?')} | {style}]")
        lines.append(f'"{text}"' if text else f'"{preview}"')
    else:
        lines.append(f'"{preview}"')
    if shot_path:
        lines.append(f"截图：{shot_path}")
    if include_guide:
        lines.append(f"（锚点规则: {_GUIDE.get(mode, '见元素描述')};"
                     "可用 open_file 工具重新打开该文件定位）")
    return "\n".join(lines)
