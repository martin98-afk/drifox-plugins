# -*- coding: utf-8 -*-
"""拾取回填文本格式化（纯函数，无 Qt 依赖，可单测）。

设计目标：让模型不靠截图也能定位元素——
- 文件给绝对路径（模型可直接用工具打开）
- 表格给全表结构化文本（列以 " | " 分隔，行以换行分隔）
- 单元格给「格文本 + 所在行 + 表格全文」三层上下文
- 段落给全文（超长截断），不再用 200 字预览
- 首次回填附锚点语义说明（#N = body 第 N 个块）
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


def format_pick(count, path_display, anchor, block, preview, shot_path, *, include_guide=False):
    """组装回填文本。anchor 含 ":r" 即表格单元格。"""
    lines = [f"📎 docx 拾取 #{count} [{path_display}]"]
    if ":r" in anchor:
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
            "可用 python-docx 遍历 body 的 w:p/w:tbl 按序定位）"
        )
    return "\n".join(lines)
