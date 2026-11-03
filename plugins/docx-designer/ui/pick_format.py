# -*- coding: utf-8 -*-
"""拾取回填文本格式化（纯函数，无 Qt 依赖，可单测）。

设计目标：让模型不靠截图也能定位元素——
- 文件给绝对路径（模型可直接用工具打开）
- 表格给全表结构化文本（列以 " | " 分隔，行以换行分隔）
- 单元格给「格文本 + 所在行 + 表格全文」三层上下文
- 段落给全文（超长截断），不再用 200 字预览
- 首次回填附锚点语义说明（#N = body 第 N 个块）
- pptx 锚点为 `幻灯片:元素`（0 起）
"""

_TEXT_CAP = 1200      # 单块文本上限
_TABLE_CAP = 3000     # 全表文本上限

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

def _is_pptx(path_display):
    return str(path_display).lower().endswith(".pptx")

def _pptx_desc(anchor):
    try:
        page, idx = anchor.split(":", 1)
        return f"[幻灯片 {int(page) + 1} 元素 {int(idx) + 1}]"
    except (ValueError, TypeError):
        return f"[元素 #{anchor}]"

def format_annotations(path_display, annotations):
    """标注统一发送文本：模型逐条按注释修改。"""
    kind = "pptx" if _is_pptx(path_display) else "docx"
    lines = [f"📝 {kind} 标注 共 {len(annotations)} 条 [{path_display}]"]
    for a in annotations:
        anchor = a.get("anchor") or "?"
        if _is_pptx(path_display):
            desc = _pptx_desc(anchor)
        elif anchor == "header":
            desc = "[页眉]"
        elif anchor == "footer":
            desc = "[页脚]"
        elif ":r" in anchor:
            base, cell = anchor.split(":", 1)
            desc = f"[表格 #{base} 单元格 {cell}]"
        else:
            desc = f"[元素 #{anchor}]"
        snippet = (a.get("snippet") or "").strip()
        lines.append(f"{_circled(int(a.get('seq') or 0))}{desc} \"{snippet}\"")
        lines.append(f"  ↳ 注释：{a.get('comment') or ''}")
        if a.get("shot"):
            lines.append(f"  截图：{a['shot']}")
    lines.append(
        "（锚点规则: #N = 文档 body 第 N 个块,从 0 数起;表格单元格 N:r行c列;"
        "header/footer = 页眉/页脚;pptx 为 幻灯片:元素;请逐条按注释修改对应元素）"
    )
    return "\n".join(lines)

def format_pick(count, path_display, anchor, block, preview, shot_path, *, include_guide=False):
    """组装回填文本。anchor 含 ":r" 即表格单元格。"""
    kind = "pptx" if _is_pptx(path_display) else "docx"
    lines = [f"📎 {kind} 拾取 #{count} [{path_display}]"]
    if _is_pptx(path_display):
        lines.append(_pptx_desc(anchor))
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
    elif anchor == "header":
        lines.append("[页眉]")
        if preview:
            lines.append(f'"{preview}"')
    elif anchor == "footer":
        lines.append("[页脚]")
        if preview:
            lines.append(f'"{preview}"')
    elif ":r" in anchor:
        base, cell = anchor.split(":", 1)
        lines.append(f"[表格 #{base} 单元格 {cell}]")
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
        lines.append(f"[表格 #{anchor}]")
        full = format_table_text(block.get("rows") or [])
        lines.append(full if full else f'"{preview}"')
    elif block is not None and block.get("kind") == "image":
        lines.append(f"[图片 #{anchor}]")
    elif block is not None:
        style = block.get("style") or block.get("kind", "?")
        text = (block.get("text") or "").strip()
        if len(text) > _TEXT_CAP:
            text = text[:_TEXT_CAP] + "…(截断)"
        lines.append(f"[{block.get('kind', '?')} #{anchor} | {style}]")
        lines.append(f'"{text}"' if text else f'"{preview}"')
    else:
        lines.append(f"[元素 #{anchor}]")
        lines.append(f'"{preview}"')
    if shot_path:
        lines.append(f"截图：{shot_path}")
    if include_guide:
        lines.append(
            "（锚点规则: #N = 文档 body 第 N 个块,从 0 数起;表格单元格 N:r行c列;"
            "header/footer = 页眉/页脚;pptx 为 幻灯片:元素;"
            "可用 python-docx 遍历 body 的 w:p/w:tbl 按序定位）"
        )
    return "\n".join(lines)
