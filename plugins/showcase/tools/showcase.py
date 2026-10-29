# -*- coding: utf-8 -*-
"""成果展示工具 — 把模型挑中的文件/图片推到消息卡片成果栏。

宿主机制：``ToolResult(artifacts=[...])`` 即自动挂成果栏（按 path 合并累积），
不需要 UI 组件，也不需要显式调 ``ui.artifacts.show``（那个通道只用于异步任务
晚于轮次结束回填原卡）。

条目契约见 ``app/widgets/inline_artifact_panel.py::_normalize_item``：
``{path, kind?, name?, width?, height?, size?, caption?, meta?}``，
kind ∈ image/video/html/text/file，缺省按扩展名推断。
"""
import os
from pathlib import Path
from typing import Any, List, Tuple

from app.tools.result import ToolResult

# 扩展名 → kind。与宿主推断表保持一致，显式给出省得两边口径漂移。
_KIND_BY_EXT = {
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".gif": "image",
    ".bmp": "image",
    ".mp4": "video",
    ".mov": "video",
    ".webm": "video",
    ".mkv": "video",
    ".avi": "video",
    ".html": "html",
    ".htm": "html",
    ".md": "text",
    ".txt": "text",
    ".json": "text",
    ".csv": "text",
    ".log": "text",
    ".py": "text",
    ".js": "text",
    ".ts": "text",
    ".yaml": "text",
    ".yml": "text",
}
# 目录展开时只收这些扩展名，避免把一个仓库的文件全推上成果栏
_PREVIEWABLE = frozenset(_KIND_BY_EXT)

# 单次推送上限：与宿主落库上限（normalize_artifact_items 50 条）对齐
MAX_ITEMS = 50


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _kind_of(path: Path) -> str:
    return _KIND_BY_EXT.get(path.suffix.lower(), "file")


def _resolve(raw: str, workdir: str) -> Path:
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = Path(workdir) / p
    return p.resolve()


def _collect(raw_paths: List[str], workdir: str) -> Tuple[List[Path], List[str]]:
    """展开参数为文件列表：目录递归取可预览文件。返回 (files, missing)。"""
    files: List[Path] = []
    missing: List[str] = []
    for raw in raw_paths:
        p = _resolve(raw, workdir)
        if p.is_dir():
            found = sorted(
                q for q in p.rglob("*") if q.is_file() and q.suffix.lower() in _PREVIEWABLE
            )
            if found:
                files.extend(found)
            else:
                missing.append(f"{raw}（目录内无可展示文件）")
        elif p.is_file():
            files.append(p)
        else:
            missing.append(raw)

    seen, uniq = set(), []
    for f in files:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    return uniq, missing


def _showcase_impl(tool_ctx, paths=None, caption: str = "", **_ignored) -> ToolResult:
    workdir = (tool_ctx or {}).get("workdir") or os.getcwd()
    raws = _as_list(paths)
    if not raws:
        return ToolResult(
            False,
            error="paths 不能为空：给要展示的文件或目录路径（相对工作目录或绝对路径）",
        )

    files, missing = _collect(raws, workdir)
    if not files:
        detail = "、".join(missing) if missing else "参数为空"
        return ToolResult(False, error=f"没有找到可展示的文件：{detail}")

    truncated = 0
    if len(files) > MAX_ITEMS:
        truncated = len(files) - MAX_ITEMS
        files = files[:MAX_ITEMS]

    # 单文件时 caption 落到条目上（成果栏能看见说明文字）；多文件时只作批次说明
    per_item_caption = caption.strip() if len(files) == 1 else ""

    items = []
    for f in files:
        kind = _kind_of(f)
        try:
            size = f.stat().st_size
        except OSError:
            size = 0
        item = {"path": str(f), "kind": kind, "name": f.name}
        if size:
            item["size"] = size
        if per_item_caption:
            item["caption"] = per_item_caption
        items.append(item)

    lines = [f"已展示 {len(items)} 个成果到成果栏"]
    if truncated:
        lines.append(f"另有 {truncated} 个超过单次上限（{MAX_ITEMS}）未展示，可再调一次传其余路径")
    if caption.strip():
        lines.append(caption.strip())
    lines.extend(f"- [{it['kind']}] {it['path']}" for it in items)
    if missing:
        lines.append("未找到：" + "、".join(missing))

    content = "\n".join(lines)
    try:
        return ToolResult(True, content=content, artifacts=items)
    except TypeError:
        # 宿主过老没有 artifacts 字段：退化成「告诉用户文件在哪」，不失败
        return ToolResult(True, content=content)


def _preview(args: dict) -> str:
    """折叠卡预览行。不要在这里做 HTML escape（主程序统一转义）。"""
    args = args or {}
    paths = _as_list(args.get("paths"))
    if not paths:
        return "展示成果"
    head = os.path.basename(paths[0].rstrip("/\\")) or paths[0]
    if len(paths) == 1:
        return f"展示 {head}"
    return f"展示 {len(paths)} 项（{head} 等）"


def _summarize(tool_name: str, tool_args: dict, content: Any) -> str:
    paths = _as_list((tool_args or {}).get("paths"))
    if not paths:
        return "展示成果"
    head = os.path.basename(paths[0].rstrip("/\\")) or paths[0]
    if len(paths) == 1:
        return f"展示了 {head}"
    return f"展示了 {len(paths)} 项（{head} 等）"


_SCHEMA = {
    "type": "function",
    "function": {
        "name": "showcase",
        "description": (
            "把文件或图片展示到用户消息卡片的成果栏。你要向用户交付成品时调用它："
            "生成的图片/视频、写好的网页、导出的报告与文档、改完待确认的文件等。"
            "传路径即可（相对工作目录或绝对路径），传目录会递归收集其中可预览的文件"
            "（图片/视频/网页/文本），单次最多 50 个。"
            "成果栏里图片显示缩略图并可点击预览，其他条目可双击用系统程序打开、拖拽导出。"
            "只在确实有成品要给人看时调用，不要用它展示源码片段或临时下载文件。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要展示的文件路径列表；也可以传目录（递归收集可预览文件）",
                },
                "caption": {
                    "type": "string",
                    "description": (
                        "可选。一句话说明这批成果是什么（如「最终版海报」「第 2 版对比图」）。"
                        "只展示单个文件时，这句话会显示在该条目上"
                    ),
                },
            },
            "required": ["paths"],
        },
    },
}


def register(registry):
    registry.register(
        "showcase",
        _SCHEMA,
        impl=_showcase_impl,
        danger="safe",
        icon="showcase",
        cn_name="展示成果",
        group="成果展示",
        description="把文件/图片展示到消息卡片成果栏",
        aliases=["Showcase", "PresentFiles"],
        render_mode="",
        preview=_preview,
        summarize=_summarize,
    )
