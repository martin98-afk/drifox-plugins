#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
workbuddy Hook Handler

在 BuildSystemPrompt 事件触发时，把 prompts/expert-prompt.md 注入到 system prompt 尾部。
实现要点：
- 通过 __file__ 定位 prompts/expert-prompt.md（不依赖环境变量，保证加载稳定）
- 把模板占位符 <PROJECT_ROOT> 替换为 HookManager 提供的 project_root
- 注入两层记忆（用户级 + 工作区）到 prompt 末尾（替代 WorkBuddy cloud memory）
- 文档建议 BuildSystemPrompt 返回静态文本以稳定会话缓存；记忆内容每会话变化，
  但仍远低于对话状态变化频率，对缓存影响可接受

CLI 调试：
  echo '{"extra_context":{"project_root":"D:/work/test"}}' \
    | python workbuddy_hook.py --event=BuildSystemPrompt
"""
import argparse
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

PLUGIN_NAME = "workbuddy"
PROMPT_REL_PATH = ("..", "prompts", "expert-prompt.md")
PROJECT_ROOT_TOKEN = "<PROJECT_ROOT>"

USER_MEMORY_DIR = Path.home() / ".drifox" / "workbuddy-mem"
USER_MEMORY_FILE = "MEMORY.md"
WORKSPACE_MEMORY_DIR_PARTS = (".drifox", "workbuddy-mem")
WORKSPACE_CURATED_FILE = "MEMORY.md"

# 单次会话加载字符上限（与提示词里声明的一致）
USER_MEMORY_LIMIT = 4000
WORKSPACE_CURATED_LIMIT = 3000
WORKSPACE_DAILY_LIMIT = 1000  # 每个日志文件最多 1000 字符
WORKSPACE_DAILY_DAYS = 7      # 最近 7 天

# Plan mode 期间被硬阻断的工具（DriFox 工具集：write/edit/multi_edit/bash/bg_start/automation_update/EnterPlanMode）
# 注意：ToolExecutor 注入 context 的 tool_name 是 Claude Code 风格（PascalCase，
# 如 Edit/Write/MultiEdit/BgStart/AutomationUpdate/EnterPlanMode），故用"去下划线+小写"
# 归一化后比较，避免大小写/下划线差异导致匹配失败（会导致阻断失效）。
_PLAN_BLOCKED_RAW = {
    "write", "edit", "multi_edit", "bash", "bg_start", "automation_update", "enterplanmode",
}
_PLAN_MODE_BLOCKED_TOOLS = frozenset(
    p.replace("_", "").lower() for p in _PLAN_BLOCKED_RAW
)
PLAN_FLAG_FILENAME = ".wb_plan_active"


def _normalize_tool_name(name: str) -> str:
    """归一化工具名：去下划线 + 转小写，用于跨 PascalCase/小写/下划线匹配"""
    return (name or "").replace("_", "").lower()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(PLUGIN_NAME)


# ============================================================
# 工具函数
# ============================================================


def get_prompt_path() -> Path:
    """定位 prompts/expert-prompt.md（相对于 hooks/ 目录）"""
    return Path(__file__).resolve().parent.joinpath(*PROMPT_REL_PATH)


def resolve_project_root(context: dict) -> str:
    """从 context 中解析项目根目录。

    BuildSystemPrompt 上下文结构：
    - extra_context: dict，含 project_root / project_name
    - 也可能在顶层（兼容写法）
    """
    extra = context.get("extra_context") or {}
    root = (
        extra.get("project_root")
        or context.get("project_root")
        or ""
    )
    return str(root) if root else ""


def load_prompt_text() -> str:
    path = get_prompt_path()
    if not path.exists():
        log.error("prompt file missing: %s", path)
        return ""
    return path.read_text(encoding="utf-8")


def _read_capped(path: Path, limit: int) -> str:
    """读取文本，超长截断并附提示"""
    if not path.exists() or not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as exc:
        log.warning("read %s failed: %s", path, exc)
        return ""
    if not text:
        return ""
    if len(text) > limit:
        return text[:limit] + f"\n\n_（已截断，原文 {len(text):,} 字符）_"
    return text


def load_user_memory() -> str:
    """读取用户级 MEMORY.md（~/.drifox/workbuddy-mem/MEMORY.md）"""
    path = USER_MEMORY_DIR / USER_MEMORY_FILE
    body = _read_capped(path, USER_MEMORY_LIMIT)
    if not body:
        return ""
    return f"## 用户级记忆（~/.drifox/workbuddy-mem/MEMORY.md）\n\n{body}"


def load_workspace_memory(project_root: str) -> str:
    """读取工作区记忆：MEMORY.md + 最近 7 天的 YYYY-MM-DD.md 日志"""
    if not project_root:
        return ""
    base = Path(project_root).joinpath(*WORKSPACE_MEMORY_DIR_PARTS)
    if not base.is_dir():
        return ""
    parts: list[str] = []

    curated = base / WORKSPACE_CURATED_FILE
    body = _read_capped(curated, WORKSPACE_CURATED_LIMIT)
    if body:
        try:
            rel = curated.relative_to(Path(project_root))
        except ValueError:
            rel = curated
        parts.append(f"### 项目长期笔记（{rel}）\n\n{body}")

    today = date.today()
    daily_blocks: list[str] = []
    for i in range(WORKSPACE_DAILY_DAYS):
        d = today - timedelta(days=i)
        p = base / f"{d.isoformat()}.md"
        body = _read_capped(p, WORKSPACE_DAILY_LIMIT)
        if body:
            daily_blocks.append(f"#### {d.isoformat()}\n\n{body}")
    if daily_blocks:
        parts.append("### 最近工作日志\n\n" + "\n\n".join(daily_blocks))

    if not parts:
        return ""
    return f"## 工作区记忆（{base}）\n\n" + "\n\n".join(parts)


def render_prompt(template: str, context: dict) -> str:
    """替换模板里的 <PROJECT_ROOT>，并追加两层记忆。"""
    root = resolve_project_root(context)
    artifact_dir = (
        f"{root}/.drifox/workbuddy-artifacts" if root else ".drifox/workbuddy-artifacts"
    )
    rendered = template.replace(PROJECT_ROOT_TOKEN, artifact_dir)

    # 注入记忆（追加到末尾）
    mem_chunks: list[str] = []
    user_mem = load_user_memory()
    workspace_mem = load_workspace_memory(root)
    if user_mem:
        mem_chunks.append(user_mem)
    if workspace_mem:
        mem_chunks.append(workspace_mem)
    if mem_chunks:
        rendered = rendered + "\n\n---\n\n# 已加载的记忆（自动注入，模型无需主动读取）\n\n" + "\n\n".join(mem_chunks)

    # 清理连续空行（连续 3+ 空行收敛为 2）
    lines = rendered.splitlines()
    cleaned: list[str] = []
    blank = 0
    for ln in lines:
        if not ln.strip():
            blank += 1
            if blank <= 1:
                cleaned.append("")
        else:
            blank = 0
            cleaned.append(ln)
    return "\n".join(cleaned).strip()


# ============================================================
# 事件处理器
# ============================================================


def handle_build_system_prompt(context: dict) -> str:
    template = load_prompt_text()
    if not template:
        return ""
    return render_prompt(template, context)


def _resolve_workdir_from_context(context: dict) -> Path | None:
    """从 hook context 中取 workdir，兼容 BuildSystemPrompt / PreToolUse 两种格式"""
    extra = context.get("extra_context") or {}
    candidates = (
        extra.get("project_root"),
        context.get("project_root"),
        extra.get("workdir"),
        context.get("workdir"),
        context.get("file"),  # PreToolUse 会带 file 字段
    )
    for c in candidates:
        if c:
            try:
                p = Path(str(c)).resolve()
                # 取首个存在的目录祖先
                while not p.is_dir():
                    if p.parent == p:
                        return None
                    p = p.parent
                return p
            except OSError:
                continue
    return None


def handle_pre_tool_use(context: dict) -> dict | None:
    """Plan mode 期间阻断 editing 类工具。

    返回 None 表示不阻断（DriFox 默认继续执行）；
    返回 {"decision": "block", "output": "..."} 表示阻断并向模型解释原因。
    """
    workdir = _resolve_workdir_from_context(context or {})
    if workdir is None:
        return None
    # 标记文件位于与工作区记忆相同的目录（wb_plan 写入此处）
    flag = workdir.joinpath(*WORKSPACE_MEMORY_DIR_PARTS) / PLAN_FLAG_FILENAME
    if not flag.exists():
        return None
    tool_name = (context.get("tool_name") or "").strip()
    # tool_name 由 ToolExecutor 规范化为 PascalCase（如 Edit/MultiEdit/BgStart），
    # 需归一化（去下划线+小写）后与阻断清单比较
    if not tool_name or _normalize_tool_name(tool_name) not in _PLAN_MODE_BLOCKED_TOOLS:
        return None
    msg = (
        f"plan mode 激活中：工具 `{tool_name}` 已被阻断。"
        f"如需修改文件请先调用 `wb_plan mode=exit` 退出计划模式。"
    )
    log.info("[workbuddy] plan-mode BLOCK tool=%s workdir=%s", tool_name, workdir)
    return {"decision": "block", "output": msg}


# ============================================================
# Python Hook 适配函数（供 hooks.json 派发）
# 签名: (event: str, context: dict) -> str | None
# ============================================================


def hook_build_system_prompt(event: str, context: dict):
    """BuildSystemPrompt 钩子入口：返回字符串会拼接到 system prompt 尾部"""
    try:
        return handle_build_system_prompt(context or {})
    except Exception as exc:  # 错误隔离：异常时返回空串，避免污染主流程
        log.exception("BuildSystemPrompt hook failed: %s", exc)
        return ""


def hook_pre_tool_use(event: str, context: dict):
    """PreToolUse 钩子入口：plan mode 阻断危险工具

    DriFox 决策约定：返回 dict 含 `decision: "block"` 即视为阻断。
    """
    try:
        return handle_pre_tool_use(context or {})
    except Exception as exc:
        log.exception("PreToolUse hook failed: %s", exc)
        return None


# ============================================================
# CLI 入口（独立调试用）
# 用法:
#   echo '{"extra_context":{"project_root":"D:/work/test"}}' \
#     | python workbuddy_hook.py --event=BuildSystemPrompt
# ============================================================


_HANDLER_MAP = {
    "BuildSystemPrompt": handle_build_system_prompt,
    "PreToolUse": handle_pre_tool_use,
}


def main():
    parser = argparse.ArgumentParser(description="workbuddy Hook Handler")
    parser.add_argument("--event", required=True, choices=list(_HANDLER_MAP.keys()))
    args = parser.parse_args()

    raw = sys.stdin.read() if not sys.stdin.isatty() else "{}"
    try:
        ctx = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        ctx = {}

    result = _HANDLER_MAP[args.event](ctx)
    if isinstance(result, dict):
        sys.stdout.write(json.dumps(result, ensure_ascii=False))
    elif isinstance(result, str):
        sys.stdout.write(result)
    else:
        sys.stdout.write("")


if __name__ == "__main__":
    main()