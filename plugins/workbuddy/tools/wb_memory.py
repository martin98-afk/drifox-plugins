# -*- coding: utf-8 -*-
"""
workbuddy wb_memory — 记忆读写工具

把 WorkBuddy 的 memory 工具体验搬进 DriFox：模型无需拼记忆文件路径、无需记住
目录约定，直接通过本工具读写两层本地记忆：

- 用户级：~/.drifox/workbuddy-mem/MEMORY.md（跨项目共享）
- 工作区：<workdir>/.drifox/workbuddy-mem/
    - MEMORY.md        项目长期笔记
    - YYYY-MM-DD.md    当日工作日志（append-only）

mode：
- read       读记忆（scope=user → 用户级；scope=workspace → 项目笔记 + 最近 7 天日志索引）
- log        追加当日工作日志（content 必填）
- note       追加项目长期笔记 MEMORY.md（content 必填）
- user_note  追加用户级 MEMORY.md（content 必填）

与 hook 注入的关系：BuildSystemPrompt 已自动注入记忆摘要；本工具用于会话中途
主动读取全文 / 写入新条目（注入内容不会自动感知会话中的写入）。
"""
import sys
import time
from datetime import date, timedelta
from pathlib import Path

_TOOLS_DIR = str(Path(__file__).resolve().parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from app.tools.registry import make_summarize_from_preview  # noqa: E402
from app.tools.result import ToolResult  # noqa: E402

GROUP_MEMORY = "记忆系统"

USER_MEM_DIR = Path.home() / ".drifox" / "workbuddy-mem"
USER_MEM_FILE = "MEMORY.md"
WS_DIR_PARTS = (".drifox", "workbuddy-mem")
READ_LIMIT = 8000          # read 单文件字符上限
DAILY_LOG_DAYS = 7         # workspace read 时列出的最近日志天数


def _norm_workdir(workdir_raw) -> Path | None:
    if not workdir_raw:
        return None
    return Path(str(workdir_raw)).resolve()


def _read_capped(path: Path, limit: int = READ_LIMIT) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    if len(text) > limit:
        return text[:limit] + f"\n\n_（已截断，原文 {len(text):,} 字符）_"
    return text


def _append(path: Path, content: str) -> int:
    """追加一段带时间戳的 markdown 条目，返回写入后文件字符数。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%H:%M:%S")
    block = f"\n### {ts}\n\n{content.strip()}\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(block)
    return len(block)


def _do_read(scope: str, ws_base: Path | None) -> ToolResult:
    if scope == "user":
        body = _read_capped(USER_MEM_DIR / USER_MEM_FILE)
        if not body:
            return ToolResult(True, content="用户级记忆为空（~/.drifox/workbuddy-mem/MEMORY.md 不存在或为空）。")
        return ToolResult(True, content=f"## 用户级记忆\n\n{body}")

    # workspace
    if ws_base is None or not ws_base.is_dir():
        return ToolResult(True, content="工作区记忆为空（当前项目尚无 .drifox/workbuddy-mem/ 目录）。")
    parts: list[str] = []
    curated = _read_capped(ws_base / "MEMORY.md")
    if curated:
        parts.append(f"### 项目长期笔记（MEMORY.md）\n\n{curated}")
    logs: list[str] = []
    today = date.today()
    for i in range(DAILY_LOG_DAYS):
        d = today - timedelta(days=i)
        p = ws_base / f"{d.isoformat()}.md"
        body = _read_capped(p)
        if body:
            logs.append(f"#### {d.isoformat()}（{p.name}）\n\n{body}")
    if logs:
        parts.append("### 最近工作日志\n\n" + "\n\n".join(logs))
    if not parts:
        return ToolResult(True, content=f"工作区记忆为空（{ws_base} 下无有效文件）。")
    return ToolResult(True, content="## 工作区记忆\n\n" + "\n\n".join(parts))


def _memory_impl(tool_ctx, **kwargs):
    workdir = _norm_workdir(tool_ctx.get("workdir") if isinstance(tool_ctx, dict) else None)
    ws_base = workdir / ".drifox" / "workbuddy-mem" if workdir else None

    mode = (kwargs.get("mode") or "").strip().lower()
    if mode not in {"read", "log", "note", "user_note"}:
        return ToolResult(False, error=f"mode 必须为 read/log/note/user_note，收到：{mode!r}")

    if mode == "read":
        scope = (kwargs.get("scope") or "workspace").strip().lower()
        if scope not in {"user", "workspace"}:
            return ToolResult(False, error=f"scope 必须为 user/workspace，收到：{scope!r}")
        return _do_read(scope, ws_base)

    content = (kwargs.get("content") or "").strip()
    if not content:
        return ToolResult(False, error=f"mode={mode} 时 content 必填")
    if len(content) > 4000:
        return ToolResult(False, error="content 超长（>4000 字符），请精简——只记有跨会话价值的内容")

    if mode == "log":
        if ws_base is None:
            return ToolResult(False, error="workdir 未提供，无法定位工作区记忆目录")
        today_log = ws_base / f"{date.today().isoformat()}.md"
        _append(today_log, content)
        return ToolResult(True, content=f"已写入当日工作日志：`{today_log}`\n\n> {content[:200]}")

    if mode == "note":
        if ws_base is None:
            return ToolResult(False, error="workdir 未提供，无法定位工作区记忆目录")
        target = ws_base / "MEMORY.md"
        _append(target, content)
        return ToolResult(True, content=f"已更新项目长期笔记：`{target}`\n\n> {content[:200]}")

    target = USER_MEM_DIR / USER_MEM_FILE
    _append(target, content)
    return ToolResult(True, content=f"已更新用户级记忆：`{target}`\n\n> {content[:200]}")


def _preview_memory(tool_args: dict) -> str:
    args = tool_args or {}
    mode = args.get("mode") or "?"
    scope = args.get("scope") or ""
    head = f"记忆操作：{mode}"
    if scope:
        head += f" ({scope})"
    content = (args.get("content") or "").strip()
    if content:
        head += f"：{content[:30]}"
    return head


_MEMORY_SCHEMA = {
    "type": "function",
    "function": {
        "name": "wb_memory",
        "description": (
            "读写 workbuddy 两层本地记忆。read=读取记忆全文（会话开头已自动注入摘要，"
            "需要完整/最新内容时用）；log=追加当日工作日志（完成实质工作后必须记录）；"
            "note=追加项目长期笔记（项目约定/技术选型）；user_note=追加用户级记忆"
            "（跨项目偏好）。替代手工拼接记忆文件路径。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["read", "log", "note", "user_note"],
                    "description": "动作：读取 / 写日志 / 写项目笔记 / 写用户级记忆",
                },
                "scope": {
                    "type": "string",
                    "enum": ["workspace", "user"],
                    "description": "仅 mode=read 时有效：workspace（默认）读项目记忆，user 读用户级记忆",
                },
                "content": {
                    "type": "string",
                    "description": "要写入的 markdown 内容（log/note/user_note 时必填），简洁、只记有跨会话价值的信息",
                },
            },
            "required": ["mode"],
        },
    },
}


def register(registry):
    """wb_memory 注册入口（PluginToolLoader 调用）"""
    registry.register(
        "wb_memory", _MEMORY_SCHEMA, impl=_memory_impl,
        danger="safe", icon="memory", cn_name="记忆读写",
        group=GROUP_MEMORY,
        description="读写 workbuddy 本地记忆（工作日志 / 项目笔记 / 用户级记忆）",
        aliases=["Memory", "memory_get", "memory_save"],
        render_mode="expand",
        preview=_preview_memory,
        summarize=make_summarize_from_preview(_preview_memory),
    )
