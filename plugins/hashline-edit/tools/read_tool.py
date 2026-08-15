# -*- coding: utf-8 -*-
"""
hashline read — 锚点输出模式（覆盖系统 read 工具）

输出 pi 格式：每行前缀 `LINE#HASH:`（如 `9#KT: console.log('world')`）；
保留 `#File:` 头格式兼容；图片走 image_data（provides_image 协议 B）；
记录 mtime（外部修改检测）+ 供 edit 校验的锚点。

与系统 read 的差异（纯锚点模式）：
- 每行自带 `LINE#HASH:` 前缀（行号+上下文哈希），show_line_numbers 参数忽略
- 哈希为三行窗口上下文哈希：相同行不同上下文不同 hash
- 新增可选 hash_width（2-4 字符，默认 2），read/edit 需一致
"""
import base64
import os
import sys
from pathlib import Path

# PluginToolLoader 用 importlib 从文件路径 exec 加载本模块（模块名带连字符前缀），
# 非标准包内导入：注入 tools/ 目录到 sys.path 后绝对导入兄弟模块。
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from app.tools.registry import make_summarize_from_preview  # noqa: E402
from app.tools.result import ToolResult  # noqa: E402

from file_io import (  # noqa: E402
    IMAGE_EXTENSIONS,
    display_path,
    is_binary,
    load_text,
    record_mtime,
    resolve,
)
from hashline_engine import DEFAULT_WIDTH, context_hash, format_line  # noqa: E402

GROUP_READ = "文件读取"

_READ_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read",
        "description": (
            "hashline 锚点读取：读文件并输出带 LINE#HASH 锚点的内容（pi 格式），"
            "供 edit 锚点编辑定位。每行格式 `行号#哈希: 内容`，哈希为三行上下文哈希，"
            "编辑行 N 只影响 N-1/N/N+1 锚点。图片返 base64。记录 mtime 检测外部修改。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "startline": {"type": "integer", "description": "起始行号 (从1开始)", "default": 1},
                "endline": {"type": "integer", "description": "结束行号(从1开始,含)。不传默认从 startline 起读 500 行"},
                "show_line_numbers": {
                    "type": "boolean",
                    "description": "兼容参数：锚点模式每行自带行号，本参数忽略",
                    "default": False,
                },
                "hash_width": {
                    "type": "integer",
                    "description": "锚点哈希宽度（2-4 字符，默认 2），需与 edit 一致",
                    "default": 2,
                },
            },
            "required": ["path"],
        },
    },
}


def _read_impl(tool_ctx, **kwargs):
    workdir = Path(tool_ctx["workdir"]) if tool_ctx.get("workdir") else None
    path = kwargs.get("path", "")
    startline = int(kwargs.get("startline") or 1)
    endline = kwargs.get("endline")
    width = int(kwargs.get("hash_width") or DEFAULT_WIDTH)
    try:
        full_path = resolve(workdir, path)
        if not full_path.exists():
            return ToolResult(False, error=f"File not found: {path}")
        if full_path.is_dir():
            return ToolResult(False, error=f"hashline read 仅支持文件（目录请用 list）：{path}")
        display = display_path(workdir, full_path, path)

        # 图片：base64 返回（视觉模型注入，协议 B）
        ext = full_path.suffix.lower()
        if ext in IMAGE_EXTENSIONS:
            img_bytes = full_path.read_bytes()
            mime_map = {
                ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
            }
            mime = mime_map.get(ext, "image/png")
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
            size_kb = len(img_bytes) / 1024
            preview = f"[图片: {display} ({size_kb:.1f} KB, {ext.upper()})]"
            record_mtime(tool_ctx, full_path)
            return ToolResult(True, content=preview, image_data={"mime": mime, "data": img_b64})

        if is_binary(full_path):
            return ToolResult(False, error=f"二进制文件不支持锚点读取：{display}")

        # 文本：分段读取（含边界上下文行），计算输出行的三行窗口哈希
        lines, _trailing = load_text(full_path)
        total = len(lines)
        start_idx = max(0, startline - 1)
        read_end = endline if endline is not None else start_idx + 500
        end_idx = min(read_end, total)
        start_ctx = max(0, start_idx - 1)
        end_ctx = min(total, read_end + 1)
        window_lines = lines[start_ctx:end_ctx]

        total_label = total if end_idx >= total else f"{end_idx}+"
        header = f"#File: {display} (Lines {startline}-{end_idx} of {total_label})"
        body = []
        for i in range(start_idx, end_idx):
            j = i - start_ctx  # window_lines 内偏移
            prev = window_lines[j - 1] if j > 0 else ""
            curr = window_lines[j]
            nxt = window_lines[j + 1] if j + 1 < len(window_lines) else ""
            h = context_hash(prev, curr, nxt, width)
            body.append(format_line(i + 1, h, curr))

        record_mtime(tool_ctx, full_path)
        content = header + ("\n" + "\n".join(body) if body else "")
        return ToolResult(True, content=content)
    except Exception as e:
        return ToolResult(False, error=f"Read error: {str(e)}")


def _preview_read(tool_args: dict) -> str:
    path = (tool_args or {}).get("path", "") or "文件"
    desc = f'读取 "{path}"'
    startline = (tool_args or {}).get("startline")
    endline = (tool_args or {}).get("endline")
    if startline is not None and endline is not None:
        desc += f" (第 {startline}-{endline} 行)"
    elif startline is not None and int(startline) > 1:
        desc += f" (从第 {startline} 行)"
    return desc


def register(registry):
    """hashline read 注册入口（覆盖系统 read）"""
    registry.register(
        "read", _READ_SCHEMA, impl=_read_impl,
        danger="safe", icon="read", cn_name="读取",
        group=GROUP_READ, description="hashline 锚点读取",
        aliases=["Read", "ReadFile", "ReadFiles", "cat"],
        render_mode="inline",
        preview=_preview_read,
        summarize=make_summarize_from_preview(_preview_read),
        # provides_image：读取图片时返回 image_data（协议 B），供视觉模型注入
        metadata={"permission_arg": "filePath", "provides_image": True},
    )
