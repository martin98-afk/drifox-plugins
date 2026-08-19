# -*- coding: utf-8 -*-
"""workbuddy wb_read_me — 智能发现并读取项目 README

行为约定：
- 从指定路径（或 workdir）向上探测 README* 文件
  （README.md / README.markdown / README.rst / README.txt / README，大小写不敏感）
- 默认最多返回 3 个；超过时按文件名优先级 + 距离排序
- >2MB 报错；>200KB 截断并附提示
- safe 工具（只读）
"""
import sys
from pathlib import Path

_TOOLS_DIR = str(Path(__file__).resolve().parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from app.tools.registry import make_summarize_from_preview  # noqa: E402
from app.tools.result import ToolResult  # noqa: E402

GROUP = "项目洞察"
README_NAMES = ("README.md", "README.markdown", "README.rst", "README.txt", "README")


def _candidate_paths(start: Path) -> list[Path]:
    """从 start 向上逐层收集 README 候选（去重，限制 8 层）"""
    seen: set[Path] = set()
    candidates: list[Path] = []
    cur = start.resolve() if start.exists() else start
    for _ in range(8):
        if not cur.exists():
            break
        try:
            for entry in cur.iterdir():
                if not entry.is_file():
                    continue
                if entry.name.lower() in {n.lower() for n in README_NAMES}:
                    rp = entry.resolve()
                    if rp not in seen:
                        seen.add(rp)
                        candidates.append(rp)
        except (PermissionError, OSError):
            pass
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    priority = {n: i for i, n in enumerate(README_NAMES)}
    candidates.sort(key=lambda p: (priority.get(p.name, 99), len(p.parts)))
    return candidates


def _readme_impl(tool_ctx, **kwargs):
    workdir_raw = tool_ctx.get("workdir") if isinstance(tool_ctx, dict) else None
    workdir = Path(workdir_raw).resolve() if workdir_raw else Path.cwd()

    path_arg = (kwargs.get("path") or "").strip()
    try:
        max_files = max(1, min(int(kwargs.get("max_files") or 3), 10))
    except (TypeError, ValueError):
        max_files = 3

    start = Path(path_arg).resolve() if path_arg else workdir
    candidates = _candidate_paths(start)
    if not candidates:
        return ToolResult(False, error=f"在 {start} 向上 8 层内未找到 README 文件")

    picked = candidates[:max_files]
    parts: list[str] = [f"## 找到 {len(picked)} 个 README（探测起点：{start}）", ""]
    for p in picked:
        try:
            size = p.stat().st_size
        except OSError as exc:
            parts.append(f"### `{p}`\n\n_无法访问：{exc}_\n")
            continue
        if size > 2 * 1024 * 1024:
            parts.append(f"### `{p}`（{size:,} 字节 — 过大，已跳过正文）\n")
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            parts.append(f"### `{p}`\n\n_读取失败：{exc}_\n")
            continue
        truncated = False
        if len(text) > 200 * 1024:
            text = text[: 200 * 1024]
            truncated = True
        header = f"### `{p}`（{size:,} 字节）"
        if truncated:
            header += " — 已截断到 200KB"
        parts.append(header + "\n\n```\n" + text + "\n```\n")
    return ToolResult(True, content="\n".join(parts).rstrip())


def _preview(tool_args: dict) -> str:
    p = (tool_args or {}).get("path") or ""
    return f"读 README：`{p or '当前项目'}`"


_README_SCHEMA = {
    "type": "function",
    "function": {
        "name": "wb_read_me",
        "description": "智能发现并读取项目 README。从指定路径或 workdir 向上扫描，返回内容与元信息。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "探测起点路径；空则用 workdir"},
                "max_files": {"type": "integer", "description": "最多返回几个 README（1–10，默认 3）", "default": 3},
            },
            "required": [],
        },
    },
}


def register(registry):
    registry.register(
        "wb_read_me", _README_SCHEMA, impl=_readme_impl,
        danger="safe", icon="read_me", cn_name="读 README",
        group=GROUP, description="向上探测并读取项目 README",
        aliases=["read_me", "ReadMe", "read_readme"],
        render_mode="expand",
        preview=_preview,
        summarize=make_summarize_from_preview(_preview),
    )