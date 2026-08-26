# -*- coding: utf-8 -*-
"""workbuddy wb_plan — 计划模式工具（enter/exit/status）

行为：
- mode=enter：写入 plan 文档到 `<workdir>/.drifox/workbuddy-mem/plan.md`，置位
  标记文件 `<workdir>/.drifox/workbuddy-mem/.wb_plan_active`，更新共享 _state。
  标记生效期间，PreToolUse hook 会硬阻断 editing 类工具
  （write/edit/multi_edit/bash/bg_start/automation_update/EnterPlanMode）
- mode=exit：清除标记 + 删除 plan 文档 + 清理 state
- mode=status：报告当前模式、plan 文件路径、进入时间

注：wb_plan 自身在 plan mode 期间仍可用（否则用户无法退出）。
"""
import json
import sys
import time
from pathlib import Path

_TOOLS_DIR = str(Path(__file__).resolve().parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from app.tools.registry import make_summarize_from_preview  # noqa: E402
from app.tools.result import ToolResult  # noqa: E402

# 注：计划状态以磁盘标记文件（.wb_plan_active）为唯一真源——
# PreToolUse hook 与 status 查询都读文件；不再引入 _state 内存镜像。
# （PluginToolLoader 会拒绝任何写 sys.modules 的工具文件，旧版
#   importlib 手动加载 _state 的方式触发该检查导致整个工具被拒载。）

GROUP = "工作流控制"
PLAN_DIR_PARTS = (".drifox", "workbuddy-mem")
PLAN_FILE_NAME = "plan.md"
PLAN_FLAG_NAME = ".wb_plan_active"


def _resolve_dir(workdir_raw) -> Path | None:
    """tool_ctx.workdir → <root>/.drifox/workbuddy-mem"""
    if not workdir_raw:
        return None
    return Path(str(workdir_raw)).resolve() / ".drifox" / "workbuddy-mem"


def _enter(workdir: Path, content: str) -> ToolResult:
    plan_path = workdir / PLAN_FILE_NAME
    flag_path = workdir / PLAN_FLAG_NAME
    workdir.mkdir(parents=True, exist_ok=True)

    plan_text = content.strip() or (
        "# 计划模式\n\n（未提供计划内容，请用 wb_plan mode=enter + plan_content 写入正式计划）\n"
    )
    ts = time.time()
    header = f"<!-- workbuddy plan-mode | entered at {ts:.0f} -->\n\n"
    plan_path.write_text(header + plan_text + "\n", encoding="utf-8")
    flag_path.write_text(
        json.dumps({"entered_at": ts, "plan_file": str(plan_path)}, ensure_ascii=False),
        encoding="utf-8",
    )

    blocked = "write / edit / multi_edit / bash / bg_start / automation_update / EnterPlanMode"
    return ToolResult(
        True,
        content=(
            f"## 计划模式已激活\n\n"
            f"- 计划文件：`{plan_path}`\n"
            f"- 标记文件：`{flag_path}`\n"
            f"- 阻断工具：**{blocked}**\n"
            f"- 允许工具：wb_plan（自身，可退出）、read/list/grep/glob/webfetch/websearch/question/skill/\n"
            f"  subagent_*/team_*/todowrite/todoread/list_skills/mcp_list_servers/\n"
            f"  wb_read_me/wb_tool_search/wb_present_files 等只读/调度类\n\n"
            f"调用 `wb_plan mode=exit` 退出并恢复全部工具。"
        ),
    )


def _exit(workdir: Path) -> ToolResult:
    flag_path = workdir / PLAN_FLAG_NAME
    plan_path = workdir / PLAN_FILE_NAME
    if not flag_path.exists() and not plan_path.exists():
        return ToolResult(True, content="未在计划模式中（标记文件不存在）。")
    if flag_path.exists():
        flag_path.unlink()
    if plan_path.exists():
        plan_path.unlink()
    return ToolResult(
        True,
        content=(
            "## 计划模式已退出\n\n"
            "- 标记文件已删除\n"
            "- 计划文档已删除\n"
            "- 所有工具已恢复可用"
        ),
    )


def _status(workdir: Path) -> ToolResult:
    flag_path = workdir / PLAN_FLAG_NAME
    plan_path = workdir / PLAN_FILE_NAME
    if not flag_path.exists():
        return ToolResult(True, content=f"未在计划模式（workdir={workdir}）。")
    try:
        meta = json.loads(flag_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        meta = {}
    entered_at = meta.get("entered_at", 0)
    return ToolResult(
        True,
        content=(
            f"## 计划模式状态：\n\n"
            f"- 进入时间：{entered_at:.0f}（{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entered_at))}）\n"
            f"- 计划文件：`{meta.get('plan_file', plan_path)}`\n"
            f"- 当前状态：**激活中**（调用 `wb_plan mode=exit` 退出）"
        ),
    )


def _plan_impl(tool_ctx, **kwargs):
    workdir_raw = tool_ctx.get("workdir") if isinstance(tool_ctx, dict) else None
    workdir = _resolve_dir(workdir_raw)
    if not workdir:
        return ToolResult(False, error="workdir 未提供，无法定位计划目录")

    mode = (kwargs.get("mode") or "").strip().lower()
    if mode not in {"enter", "exit", "status"}:
        return ToolResult(False, error=f"mode 必须为 enter/exit/status，收到：{mode!r}")

    if mode == "enter":
        return _enter(workdir, kwargs.get("plan_content") or "")
    if mode == "exit":
        return _exit(workdir)
    return _status(workdir)


def _preview(tool_args: dict) -> str:
    mode = (tool_args or {}).get("mode", "")
    return f"计划模式：{mode or '?'}"


_PLAN_SCHEMA = {
    "type": "function",
    "function": {
        "name": "wb_plan",
        "description": (
            "进入/退出/查询计划模式。enter 后只读工具与 wb_plan 自身可用，"
            "写文件、执行命令等会被 PreToolUse 硬阻断；exit 恢复全部工具。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["enter", "exit", "status"],
                    "description": "模式动作",
                },
                "plan_content": {
                    "type": "string",
                    "description": "（enter 时）计划内容，写入 plan.md",
                },
            },
            "required": ["mode"],
        },
    },
}


def register(registry):
    registry.register(
        "wb_plan", _PLAN_SCHEMA, impl=_plan_impl,
        danger="safe", icon="plan", cn_name="计划模式",
        group=GROUP, description="进入/退出计划模式（写/编辑/命令类工具被硬阻断）",
        aliases=["plan", "Plan", "PlanMode", "wb_enter_plan_mode", "wb_exit_plan_mode"],
        render_mode="expand",
        preview=_preview,
        summarize=make_summarize_from_preview(_preview),
    )