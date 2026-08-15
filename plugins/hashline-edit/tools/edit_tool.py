# -*- coding: utf-8 -*-
"""
hashline edit / multi_edit — 纯锚点模式编辑（覆盖系统 edit/multi_edit）

核心契约（用户拍板）：
- **纯锚点模式**：无 oldString/newString 文本兼容路径，全部基于 read 输出的
  `LINE#HASH` 锚点定位
- 所有编辑对同一 pre-edit 快照校验，**自底向上**应用（pos 行号降序）
- 陈旧锚点（hash 不匹配）→ E_STALE_ANCHOR，绝不静默移位
- lines 含显示前缀/diff 标记 → E_INVALID_PATCH；连续 3 次相同 no-op → E_NOOP_LOOP
- 编辑前校验 mtime（外部修改检测）
- 成功后返回 unified diff + `--- Anchors A-B ---` 新锚点块（ToolResult.anchors，
  供 LLM 链式编辑）
"""
import difflib
import os
import sys
from pathlib import Path

# PluginToolLoader 用 importlib 从文件路径 exec 加载本模块（模块名带连字符前缀），
# 非标准包内导入：注入 tools/ 目录到 sys.path 后绝对导入兄弟模块。
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from app.tools.result import ToolResult  # noqa: E402

from file_io import (  # noqa: E402
    check_modified,
    display_path,
    is_binary,
    load_text,
    record_mtime,
    resolve,
)
from hashline_engine import DEFAULT_WIDTH  # noqa: E402
from snapshot import (  # noqa: E402
    apply_edits,
    build_anchors,
    _edit_sig,
    note_noop,
    reset_noop,
)

GROUP_WRITE = "文件写入"


# ========== schema（edit / multi_edit 共用 edits 结构） ==========

_EDIT_ITEMS_SCHEMA = {
    "type": "object",
    "properties": {
        "op": {
            "type": "string",
            "enum": ["replace", "append", "prepend", "replace_text"],
            "description": (
                "操作类型：replace=整行替换（lines 为新行内容，可多行）；"
                "append=行尾追加（content）；prepend=行首插入（content）；"
                "replace_text=行内文本替换（content 为 JSON 字符串 {\"old\":..,\"new\":..}）"
            ),
        },
        "pos": {
            "type": "string",
            "description": "锚点 LINE#HASH（read 输出），如 9#KT",
        },
        "end": {
            "type": "string",
            "description": "区间结束锚点（仅 replace：多行替换/删除 [pos, end] 区间）",
        },
        "lines": {
            "type": "array",
            "items": {"type": "string"},
            "description": "replace 的新行内容（不允许含锚点前缀或 diff 标记）",
        },
        "content": {
            "type": "string",
            "description": (
                "append/prepend 的追加/插入文本；replace_text 时为 JSON 字符串 "
                "{\"old\":\"..\",\"new\":\"..\"}（old 需在目标行唯一）"
            ),
        },
        "textHint": {
            "type": "string",
            "description": "可选第二因子：目标行内容前缀，防止陈旧锚点误编辑",
        },
    },
    "required": ["op", "pos"],
}

_EDIT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "edit",
        "description": (
            "hashline 锚点编辑：基于 read 输出的 LINE#HASH 锚点精准编辑（纯锚点模式，"
            "无 oldString 兼容路径）。支持 replace/append/prepend/replace_text；"
            "多编辑点对同一 pre-edit 快照校验、自底向上应用；陈旧锚点报 E_STALE_ANCHOR "
            "提示重读；成功后返回 diff + 新锚点块供链式编辑。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径（建议先用 read 读取）"},
                "edits": {
                    "type": "array",
                    "description": "编辑列表（1 个或多个），每项 {op, pos, end?, lines?, content?, textHint?}",
                    "items": _EDIT_ITEMS_SCHEMA,
                },
                "hash_width": {
                    "type": "integer",
                    "description": "锚点哈希宽度（2-4 字符，默认 2），需与 read 一致",
                    "default": 2,
                },
            },
            "required": ["path", "edits"],
        },
    },
}

_MULTI_EDIT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "multi_edit",
        "description": (
            "hashline 批量锚点编辑：一次对同一文件应用多个锚点编辑点（纯锚点模式）。"
            "全部编辑对同一 pre-edit 快照校验，任一锚点陈旧则整体拒绝（不部分应用）；"
            "自底向上应用；成功后返回 unified diff + 新锚点块供链式编辑。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径（建议先用 read 读取）"},
                "edits": {
                    "type": "array",
                    "description": "批量编辑列表，每项 {op, pos, end?, lines?, content?, textHint?}",
                    "items": _EDIT_ITEMS_SCHEMA,
                },
                "hash_width": {
                    "type": "integer",
                    "description": "锚点哈希宽度（2-4 字符，默认 2），需与 read 一致",
                    "default": 2,
                },
            },
            "required": ["path", "edits"],
        },
    },
}


# ========== 核心编辑逻辑（edit / multi_edit 共用） ==========


def _edit_core(tool_ctx, kwargs, tool_name: str) -> ToolResult:
    workdir = Path(tool_ctx["workdir"]) if tool_ctx.get("workdir") else None
    path = kwargs.get("path", "")
    edits = kwargs.get("edits", [])
    width = int(kwargs.get("hash_width") or DEFAULT_WIDTH)
    try:
        full_path = resolve(workdir, path)
        if not full_path.exists():
            return ToolResult(False, error=f"File not found: {path}")
        if full_path.is_dir():
            return ToolResult(False, error=f"目录不可编辑（hashline edit 仅支持文件）：{path}")
        display = display_path(workdir, full_path, path)
        if is_binary(full_path):
            return ToolResult(False, error=f"二进制文件不支持锚点编辑：{display}")

        # 外部修改检测（read 后 mtime 变化则拒绝）
        check = check_modified(tool_ctx, workdir, full_path, path)
        if check:
            return ToolResult(False, error=check)

        old_lines, trailing = load_text(full_path)
        new_lines, meta = apply_edits(old_lines, edits, width)

        if meta["errors"]:
            return ToolResult(
                False,
                error="\n".join(meta["errors"]) + "\n文件未做任何修改，请重新 read 拿最新锚点后重试。",
            )

        sig = _edit_sig(edits)
        if meta["noop"]:
            # no-op：不写文件；连续 3 次相同 no-op → E_NOOP_LOOP
            noop_err = note_noop(tool_ctx, full_path, sig)
            if noop_err:
                return ToolResult(False, error=noop_err)
            return ToolResult(
                True,
                content=f"已编辑 {display}：编辑内容与原内容一致（no-op），未写文件。请确认编辑目标后重试。",
            )
        reset_noop(tool_ctx, full_path)

        # 写文件（保留原行尾结构）
        new_text = "\n".join(new_lines) + ("\n" if trailing else "")
        full_path.write_text(new_text, encoding="utf-8")
        record_mtime(tool_ctx, full_path)

        # unified diff
        old_text = "\n".join(old_lines) + ("\n" if trailing else "")
        diff_lines = list(
            difflib.unified_diff(
                old_text.splitlines(), new_text.splitlines(),
                fromfile=path, tofile=path, lineterm="",
            )
        )
        diff_str = "\n".join(diff_lines) if diff_lines else ""

        # 链式锚点块（受影响行窗口）
        anchors = build_anchors(new_lines, meta["affected"], width)
        count = len(meta["applied"])
        content = f"已编辑 {display}（{count} 处锚点编辑成功）"
        return ToolResult(True, content=content, diff=diff_str, anchors=anchors)
    except Exception as e:
        return ToolResult(False, error=f"{tool_name} error: {str(e)}")


def _edit_impl(tool_ctx, **kwargs):
    return _edit_core(tool_ctx, kwargs, "Edit")


def _multi_edit_impl(tool_ctx, **kwargs):
    return _edit_core(tool_ctx, kwargs, "MultiEdit")


# ========== 渲染闭包 ==========


def _render_diff_body(result, tool_name, tool_args, success):
    """编辑类工具（edit/multi_edit）完成框渲染闭包：inline diff 预览

    与系统 file_tools._render_edit_diff_body 同款实现（从主程序 render_helpers
    迁出的封装）：复用 app.widgets.render_helpers 的 _render_diff_preview
    （行号/词级差异高亮/增删配色/hunk 高亮）+ _summarize_diff（+N/-N 统计），
    保证差异框渲染与系统工具完全一致。返回 None 时渲染层回退通用渲染。
    """
    import os

    from app.widgets.render_helpers import (
        _get_global_font,
        _render_diff_preview,
        _summarize_diff,
        escape,
        get_font_family_css,
        scale_font_size,
    )

    diff = getattr(result, "diff", None) or ""
    if not diff:
        return None  # 无 diff → 回退默认
    diff_summary = _summarize_diff(diff)
    diff_body = _render_diff_preview(diff)
    diff_files = diff_summary["files"]
    file_label = diff_files[0] if diff_files else "文件变更"
    file_label = os.path.basename(file_label)
    if len(diff_files) > 1:
        file_label = f"{file_label} 等 {len(diff_files)} 个文件"
    added = diff_summary["added"]
    deleted = diff_summary["deleted"]
    _gf = _get_global_font()
    return f"""
    <div class="tool-diff-inline">
        <div class="tool-diff-inline__header" style="{get_font_family_css()}">
            <span class="tool-diff-inline__file" title="{escape(file_label)}">{escape(file_label)}</span>
            <span class="tool-diff-inline__summary">
                <span class="tool-diff-inline__add" style="color: #56d364;">+{added}</span>
                <span class="tool-diff-inline__del" style="color: #ff7b72;">-{deleted}</span>
            </span>
        </div>
        <div class="tool-diff-inline__body" style="font-family: '{_gf}', Consolas, 'Courier New', monospace; font-size: {scale_font_size(12)}px;">
            {diff_body}
        </div>
    </div>"""


def _preview_edit(tool_args: dict) -> str:
    path = (tool_args or {}).get("path", "") or "文件"
    edits = (tool_args or {}).get("edits", [])
    n = len(edits) if isinstance(edits, list) else 0
    return f'编辑 "{path}"（{n} 处锚点编辑）'


def _preview_multi_edit(tool_args: dict) -> str:
    path = (tool_args or {}).get("path", "") or "文件"
    edits = (tool_args or {}).get("edits", [])
    n = len(edits) if isinstance(edits, list) else 0
    return f'批量编辑 "{path}"（{n} 处）'


def _summarize_edit(tool_name: str):
    """编辑类工具压缩摘要（从主程序 history_compactor 迁出语义）"""

    def _summarize(name, tool_args, tool_content):
        path = (tool_args or {}).get("path", "?")
        edits = (tool_args or {}).get("edits", [])
        n = len(edits) if isinstance(edits, list) else 0
        content_len = len(tool_content or "")
        return f"[{name}] anchor-edit {path} ({n} ops, {content_len:,} chars)"

    return _summarize


# ========== 注册入口 ==========


def register(registry):
    """hashline edit / multi_edit 注册入口（覆盖系统 edit/multi_edit）"""
    registry.register(
        "edit", _EDIT_SCHEMA, impl=_edit_impl,
        danger="dangerous", icon="编辑", cn_name="编辑",
        group=GROUP_WRITE, description="hashline 锚点编辑（纯锚点模式）",
        aliases=["Edit", "TextEdit", "ReplaceInFile", "replace"],
        render=_render_diff_body,
        preview=_preview_edit,
        summarize=_summarize_edit("edit"),
        # reconstruct_diff：历史消息 diff 缺失时，渲染层按 operations 参数重建伪 diff
        metadata={"permission_arg": "filePath", "reconstruct_diff": True},
    )
    registry.register(
        "multi_edit", _MULTI_EDIT_SCHEMA, impl=_multi_edit_impl,
        danger="dangerous", icon="编辑", cn_name="批量编辑",
        group=GROUP_WRITE, description="hashline 批量锚点编辑",
        aliases=["MultiEdit", "MultiEditTool"],
        render=_render_diff_body,
        preview=_preview_multi_edit,
        summarize=_summarize_edit("multi_edit"),
        metadata={"permission_arg": "filePath"},
    )
