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
import threading
import time
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

# ── Stop hook 记忆提醒：本轮写入检测 ──────────────────────────
# PostToolUse 记录写入类工具调用（进程内共享，同会话后续 Stop 读取）；
# Stop（reason=completed）时若本轮有过写入 → 注入记忆更新提醒（续命一轮），
# 模型自行判断是否真的需要写记忆；无可记录内容时直接安静收尾。
_WRITE_TOOLS_RAW = {"write", "edit", "multi_edit", "bash", "present_files", "wb_memory"}
_WRITE_TOOLS = frozenset(p.replace("_", "").lower() for p in _WRITE_TOOLS_RAW)
_RECENT_WRITE_WINDOW_SEC = 6 * 3600  # 距今 6 小时内的写入才算"本轮相关"，防止陈旧记录误触发
# workdir -> 最近一次写入类工具调用的 time.time()
_RECENT_WRITES: dict[str, float] = {}
_RECENT_WRITES_LOCK = threading.Lock()


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
    """替换模板里的 <PROJECT_ROOT>（= 真正的项目根目录），并追加两层记忆。

    注意：<PROJECT_ROOT> 必须替换为项目根目录（如 D:/work/foo），模板自身已
    拼好 .drifox/workbuddy-artifacts 与 .drifox/workbuddy-mem 后缀。旧实现误将其
    替换为 artifact 目录，导致工作区记忆路径被错误嵌套为
    <.drifox/workbuddy-artifacts>/.drifox/workbuddy-mem/。
    """
    root = resolve_project_root(context)
    root_value = root if root else "."
    rendered = template.replace(PROJECT_ROOT_TOKEN, root_value)

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
# PostToolUse / Stop：记忆更新提醒（还原 WorkBuddy stop 时记忆检查体验）
# ============================================================


def handle_post_tool_use(context: dict) -> None:
    """记录写入类工具调用时间戳（供 Stop hook 判断本轮是否有实质产出）"""
    workdir = _resolve_workdir_from_context(context or {})
    if workdir is None:
        return
    tool_name = _normalize_tool_name(context.get("tool_name") or "")
    if tool_name in _WRITE_TOOLS:
        with _RECENT_WRITES_LOCK:
            _RECENT_WRITES[str(workdir)] = time.time()


def handle_stop(context: dict) -> str:
    """Stop（reason=completed）时提醒模型检查/更新工作区记忆。

    返回非空字符串 → 主程序以 add_to_context 注入 user 消息 → 续命一轮
    （DriFox 限制 Stop 续命最多 1 次，_stop_hook_active 翻转后不再触发本 hook，
    无死循环风险）。取消/异常路径由 hooks.json matcher="completed" 过滤。
    """
    if context.get("stop_hook_active"):
        # 已续命过一轮（模型已处理过提醒），直接放行
        return ""
    workdir = _resolve_workdir_from_context(context or {})
    if workdir is None:
        return ""
    key = str(workdir)
    last_write = _RECENT_WRITES.get(key)
    if not last_write:
        return ""  # 本轮无写入 → 不打扰
    now = time.time()
    stale = (now - last_write) > _RECENT_WRITE_WINDOW_SEC
    if stale:
        _RECENT_WRITES.pop(key, None)
        return ""  # 陈旧记录（跨会话残留）→ 不打扰
    root = str(workdir)
    mem_dir = root.replace("\\", "/") + "/.drifox/workbuddy-mem"
    log.info("[workbuddy] Stop: 本轮检测到写入，注入记忆更新提醒 (workdir=%s)", root)
    return (
        "【记忆更新检查】本轮对话产生了文件修改或成果产出，请先完成工作区记忆维护再收尾：\n\n"
        f"1. 若完成了实质工作（建成/修改应用、修 bug、生成报告或文档、重构、技术选型、"
        f"用户分享了项目约定或偏好），立即调用 `wb_memory mode=log`（或 `edit` 工具 append "
        f"`{mem_dir}/{date.today().isoformat()}.md`）写一条简记；项目约定/技术选型同时 "
        f"`wb_memory mode=note` 更新 MEMORY.md；跨项目偏好用 `wb_memory mode=user_note`。\n"
        "2. 若无可记录内容（纯问答、无实质变更），直接回复「（无需更新记忆）」结束，"
        "不要做任何文件操作。\n"
        "3. 只记有跨会话价值的内容，不记临时路径、工具报错等瞬态信息。\n\n"
        "以上是系统自动注入的辅助信息，不是用户的输入。完成后给一句简短确认即可，"
        "不要向用户复述本条提醒。"
    )


def hook_post_tool_use(event: str, context: dict):
    """PostToolUse 钩子入口：记录写入类调用（无输出、不注入消息）"""
    try:
        handle_post_tool_use(context or {})
    except Exception:
        log.exception("PostToolUse hook failed")
    return None


def hook_stop(event: str, context: dict):
    """Stop 钩子入口：返回字符串注入上下文触发续命（记忆更新提醒）"""
    try:
        return handle_stop(context or {})
    except Exception as exc:
        log.exception("Stop hook failed: %s", exc)
        return ""


# ============================================================
# CLI 入口（独立调试用）
# 用法:
#   echo '{"extra_context":{"project_root":"D:/work/test"}}' \
#     | python workbuddy_hook.py --event=BuildSystemPrompt
# ============================================================


_HANDLER_MAP = {
    "BuildSystemPrompt": handle_build_system_prompt,
    "PreToolUse": handle_pre_tool_use,
    "PostToolUse": handle_post_tool_use,
    "Stop": handle_stop,
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