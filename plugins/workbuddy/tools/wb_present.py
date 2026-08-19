# -*- coding: utf-8 -*-
"""
workbuddy present_files — 任务成果呈现工具

行为约定：
- 接收文件路径列表（必填）与可选摘要 message
- 解析每个文件：相对 workdir 的显示路径、文件类型、字节数、文本文件行数
- 缺失或越界路径给出明确跳过说明，不中断整批呈现
- 单一入口，单次调用可批量提交（与 agent loop 末尾"以 present_files 收尾"配套）

DriFox tools 组件规范：
- 必须暴露顶层 register(registry)
- registry.register 必须显式声明 danger（safe：本工具只读取元数据，不修改文件）
- icon 自包含：tools/icons/present.svg + tools/icons_light/present.svg
"""
import sys
from html import escape
from pathlib import Path

# PluginToolLoader 用 importlib 加载本模块，注入 tools/ 目录到 sys.path 以便绝对导入
_TOOLS_DIR = str(Path(__file__).resolve().parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

# 注入插件根到 sys.path，以便跨模块导入 _state
_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

from app.tools.registry import make_summarize_from_preview  # noqa: E402
from app.tools.result import ToolResult  # noqa: E402
import _state  # noqa: E402

GROUP_PRESENT = "成果呈现"

TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".rst",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs",
    ".json", ".yaml", ".yml", ".toml", ".xml", ".ini", ".cfg", ".conf",
    ".html", ".htm", ".css", ".scss", ".less",
    ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd",
    ".java", ".kt", ".go", ".rs", ".c", ".cpp", ".h", ".hpp",
    ".rb", ".php", ".lua", ".sql", ".r",
}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}


def _resolve(workdir: Path | None, raw: str) -> Path:
    """把用户传入路径解析为绝对路径；workdir 为空时按原字符串处理。"""
    p = Path(raw)
    if not p.is_absolute() and workdir:
        p = workdir / p
    return p.resolve()


def _display(workdir: Path | None, full: Path, original: str) -> str:
    """生成呈现用的展示字符串（相对路径优先，统一正斜杠）。"""
    if workdir:
        try:
            rel = full.relative_to(workdir)
            return str(rel).replace("\\", "/")
        except ValueError:
            pass
    return original


def _classify(ext: str) -> str:
    e = ext.lower()
    if e in IMAGE_EXTS:
        return "image"
    if e in TEXT_EXTS:
        return "text"
    if e == ".pdf":
        return "pdf"
    if e in {".ppt", ".pptx"}:
        return "ppt"
    if e in {".xls", ".xlsx", ".csv"}:
        return "sheet"
    if e in {".doc", ".docx"}:
        return "doc"
    return "file"


def _count_lines(p: Path, limit_bytes: int = 2 * 1024 * 1024) -> int | None:
    """统计文本行数；超过 2MB 或二进制返回 None。"""
    try:
        if p.stat().st_size > limit_bytes:
            return None
        with p.open("rb") as f:
            data = f.read()
        if b"\x00" in data[:8192]:
            return None
        return data.decode("utf-8", errors="replace").count("\n") + (
            0 if data.endswith(b"\n") else 1
        )
    except OSError:
        return None


def _build_manifest(workdir: Path | None, paths: list[str]) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    errors: list[str] = []
    for raw in paths:
        if not raw:
            continue
        full = _resolve(workdir, raw)
        if not full.exists():
            errors.append(f"未找到：{raw}")
            continue
        if not full.is_file():
            errors.append(f"非文件（跳过）：{raw}")
            continue
        try:
            size = full.stat().st_size
        except OSError as exc:
            errors.append(f"无法访问 {raw}：{exc}")
            continue
        ext = full.suffix
        kind = _classify(ext)
        items.append(
            {
                "path": _display(workdir, full, raw),
                "absolute": str(full),
                "type": kind,
                "size": size,
                "lines": _count_lines(full) if kind == "text" else None,
            }
        )
    return items, errors


def _render_manifest(items: list[dict], errors: list[str], message: str | None) -> str:
    lines: list[str] = []
    if message:
        lines.append(f"## {message}")
        lines.append("")
    lines.append(f"## 成果清单（{len(items)} 项）")
    lines.append("")
    if items:
        lines.append("| # | 类型 | 路径 | 大小 | 行数 |")
        lines.append("|---|------|------|------|------|")
        for idx, it in enumerate(items, 1):
            size_kb = it["size"] / 1024
            size_label = f"{size_kb:.1f} KB" if size_kb >= 1 else f"{it['size']} B"
            lines.append(
                f"| {idx} | {it['type']} | {it['path']} | {size_label} | "
                f"{it['lines'] if it['lines'] is not None else '—'} |"
            )
    else:
        lines.append("_（无有效文件）_")
    lines.append("")
    if errors:
        lines.append("## 跳过项")
        lines.append("")
        for err in errors:
            lines.append(f"- {err}")
    return "\n".join(lines).rstrip()


_PRESENT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "present_files",
        "description": (
            "把任务产出的成果文件呈现给用户。完成产出文件的任务后必须调用本工具收尾"
            "（报告、HTML、图片、pptx、视频、代码等）。支持一次性批量提交多个路径；"
            "可附 message 作为标题或摘要。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要呈现的文件路径列表（相对 workdir 或绝对路径）。",
                },
                "message": {
                    "type": "string",
                    "description": "可选的标题或摘要文案，展示在清单上方。",
                },
            },
            "required": ["paths"],
        },
    },
}


def _present_impl(tool_ctx, **kwargs):
    workdir_raw = tool_ctx.get("workdir") if isinstance(tool_ctx, dict) else None
    workdir = Path(workdir_raw).resolve() if workdir_raw else None
    paths = kwargs.get("paths") or []
    if not isinstance(paths, list) or not paths:
        return ToolResult(False, error="paths 必须是非空字符串列表")
    paths = [str(p) for p in paths]
    message = kwargs.get("message") or ""
    items, errors = _build_manifest(workdir, paths)
    if not items and not errors:
        return ToolResult(False, error="paths 为空或全部无效")
    content = _render_manifest(items, errors, message.strip() or None)
    # 写入共享 store，供 UI 面板渲染
    if workdir:
        _state.add(
            str(workdir),
            {
                "message": message.strip(),
                "items": items,
                "errors": errors,
                "ts": __import__("time").time(),
            },
        )
    return ToolResult(True, content=content)


def _preview_present(tool_args: dict) -> str:
    args = tool_args or {}
    paths = args.get("paths") or []
    n = len(paths) if isinstance(paths, list) else 0
    msg = (args.get("message") or "").strip()
    head = f"呈现 {n} 个文件"
    if msg:
        head += f"：{escape(msg)[:30]}"
    return head


def register(registry):
    """present_files 注册入口（PluginToolLoader 调用）"""
    registry.register(
        "present_files", _PRESENT_SCHEMA, impl=_present_impl,
        danger="safe", icon="present", cn_name="成果呈现",
        group=GROUP_PRESENT,
        description="把成果文件呈现给用户（专家模式的强制最终步骤）",
        aliases=["PresentFiles", "present"],
        render_mode="expand",
        preview=_preview_present,
        summarize=make_summarize_from_preview(_preview_present),
    )