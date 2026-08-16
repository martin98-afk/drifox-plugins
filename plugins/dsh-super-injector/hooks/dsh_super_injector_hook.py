#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dsh-super-injector Hook Handler

运行时注入状态管理（源自 dsh-super-injector，DriFox 重写版）：

- SessionStart           初始化状态文件 + 写会话开始记录
- PostToolUse            审计日志（工具名/文件/结果摘要）+ 轻量异常检测（不调 LLM）
- PostAssistantMessage   记录模型回复摘要（assistant_response/response 探测）
- Stop                   会话统计收尾（工具调用数/告警数/起止时间）
- BuildSystemPrompt      返回静态能力声明（会话构建时注入 system prompt 尾部）

关键约束（drifox hooks 以 subprocess 每次全新调用，无内存共享）：
- 观测型 hook（SessionStart/PostToolUse/PostAssistantMessage/Stop）返回**空串**，
  避免返回值被注入 session.messages（DriFox 消息级 hook 会拼接收回值进消息流）；
  审计/统计全部走 memory/ 文件落盘。BuildSystemPrompt 除外（声明文本注入 system
  prompt 尾部是设计行为）。
- 所有状态必须落盘 memory/ 目录 JSON 文件
- 全部幂等（可重复触发）
- JSON 原子写（tmp + rename）
- 单次执行控制在超时（15s）内
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PLUGIN_NAME = "dsh-super-injector"
STATE_FILENAME = "dsh-super-injector-state.json"
AUDIT_FILENAME = "dsh-super-injector-audit.jsonl"
WARN_FILENAME = "dsh-super-injector-warnings.jsonl"
SUMMARY_MAX = 500

# BuildSystemPrompt 静态能力声明（静态到头：不随状态变，会话缓存稳定）
SYSTEM_PROMPT_DECLARATION = (
    "本环境装有 dsh-super-injector（会话审计 hooks + 插件状态工具）："
    "会话审计与插件状态管理——SessionStart/PostToolUse/PostAssistantMessage/Stop "
    "审计落盘 memory/，插件状态查询/自检/能力声明三个工具"
    "（dsh_injector_info / dsh_plugin_status / dsh_plugin_self_test）。"
    "插件自身的提示词/工具/钩子皆可自我优化；"
    "从零体验路径：dsh_plugin_status → dsh_plugin_self_test → dsh_injector_info。"
)


# ============================================================
# 工具函数
# ============================================================


def get_project_root(ctx: dict) -> Path | None:
    """project_root 为空时返回 None（调用方跳过写盘，避免污染工作目录）。"""
    root = ctx.get("project_root", "")
    if root:
        return Path(root)
    return None


def _memory_dir(project_root: Path) -> Path:
    d = project_root / "memory"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _state_path(project_root: Path) -> Path:
    return _memory_dir(project_root) / STATE_FILENAME


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def atomic_write_json(path: Path, data: dict) -> None:
    """JSON 原子写：先写 tmp 再 rename（避免半截文件被读取）。"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def append_jsonl(path: Path, record: dict) -> None:
    """追加一行 JSONL（单行写入，天然原子）。"""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ============================================================
# 事件处理器
# ============================================================


def handle_session_start(ctx: dict) -> None:
    """SessionStart：初始化状态文件 + 写会话开始记录（幂等：覆盖写）。"""
    project_root = get_project_root(ctx)
    if project_root is None:
        return
    mem = _memory_dir(project_root)
    state = {
        "plugin": PLUGIN_NAME,
        "session_started_at": _now_iso(),
        "tool_calls": 0,
        "warnings": 0,
        "last_updated": _now_iso(),
    }
    atomic_write_json(_state_path(project_root), state)
    append_jsonl(
        mem / AUDIT_FILENAME,
        {"event": "SessionStart", "at": _now_iso(), "project": str(project_root)},
    )


def _tool_result(ctx: dict) -> str:
    """结果摘要：探测 result_success / tool_result.has_error 字段。"""
    if ctx.get("result_success") is False:
        return "failure"
    if isinstance(ctx.get("tool_result"), dict) and ctx["tool_result"].get("has_error"):
        return "error"
    return "ok"


def handle_post_tool_use(ctx: dict) -> None:
    """PostToolUse：审计日志 + 轻量异常检测（不调 LLM，命中即写告警日志）。"""
    project_root = get_project_root(ctx)
    if project_root is None:
        return
    mem = _memory_dir(project_root)
    record = {
        "event": "PostToolUse",
        "at": _now_iso(),
        "tool_name": ctx.get("tool_name", "unknown"),
        "file": ctx.get("file", ""),
        "result": _tool_result(ctx),
    }
    append_jsonl(mem / AUDIT_FILENAME, record)

    abnormal = record["result"] in ("error", "failure")
    if abnormal:
        append_jsonl(
            mem / WARN_FILENAME,
            {
                "event": "PostToolUse",
                "at": record["at"],
                "tool_name": record["tool_name"],
                "file": record["file"],
                "reason": f"tool result indicates {record['result']}",
            },
        )

    # 状态计数更新（读-改-原子写，幂等）
    state = load_json(_state_path(project_root))
    state["tool_calls"] = state.get("tool_calls", 0) + 1
    state["warnings"] = state.get("warnings", 0) + (1 if abnormal else 0)
    state["last_updated"] = _now_iso()
    atomic_write_json(_state_path(project_root), state)


def handle_post_assistant_message(ctx: dict) -> None:
    """PostAssistantMessage：记录模型回复摘要（降级探测字段）。"""
    project_root = get_project_root(ctx)
    if project_root is None:
        return
    msg = ""
    for key in ("assistant_response", "response"):
        value = ctx.get(key)
        if isinstance(value, str) and value.strip():
            msg = value.strip()
            break
    append_jsonl(
        _memory_dir(project_root) / AUDIT_FILENAME,
        {
            "event": "PostAssistantMessage",
            "at": _now_iso(),
            "summary": msg[:SUMMARY_MAX] or "(empty)",
        },
    )


def handle_stop(ctx: dict) -> None:
    """Stop：会话统计收尾（工具调用数/告警数/结束时间，幂等：覆盖写）。"""
    project_root = get_project_root(ctx)
    if project_root is None:
        return
    mem = _memory_dir(project_root)
    state = load_json(_state_path(project_root))
    state["session_ended_at"] = _now_iso()
    state["tool_calls"] = state.get("tool_calls", 0)
    state["warnings"] = state.get("warnings", 0)
    atomic_write_json(_state_path(project_root), state)
    append_jsonl(
        mem / AUDIT_FILENAME,
        {
            "event": "Stop",
            "at": _now_iso(),
            "tool_calls": state.get("tool_calls", 0),
            "warnings": state.get("warnings", 0),
        },
    )


# ============================================================
# Python Hook 适配函数（供 hooks.json 派发）
# 签名: (event: str, context: dict) -> str | None
# ============================================================


def hook_session_start(event: str, context: dict) -> str:
    """观测型 hook：返回空串避免注入消息流（审计走文件落盘）。"""
    handle_session_start(context)
    return ""


def hook_post_tool_use(event: str, context: dict) -> str:
    """观测型 hook：返回空串避免注入消息流（审计走文件落盘）。"""
    handle_post_tool_use(context)
    return ""


def hook_post_assistant_message(event: str, context: dict) -> str:
    """观测型 hook：返回空串避免注入消息流（审计走文件落盘）。"""
    handle_post_assistant_message(context)
    return ""


def hook_stop(event: str, context: dict) -> str:
    """观测型 hook：返回空串避免注入消息流（统计走文件落盘）。"""
    handle_stop(context)
    return ""


def hook_build_system_prompt(event: str, context: dict) -> str:
    """BuildSystemPrompt：返回静态能力声明（静态到头，会话缓存稳定）。"""
    return SYSTEM_PROMPT_DECLARATION


def handle_build_system_prompt(ctx: dict) -> str:
    """CLI 调试用：返回能力声明文本。"""
    return SYSTEM_PROMPT_DECLARATION


# ============================================================
# CLI 入口（独立调试用）
# 用法:
#   echo '{}' | python dsh_super_injector_hook.py --event=SessionStart
# ============================================================


_HANDLER_MAP = {
    "SessionStart": handle_session_start,
    "PostToolUse": handle_post_tool_use,
    "PostAssistantMessage": handle_post_assistant_message,
    "Stop": handle_stop,
    "BuildSystemPrompt": handle_build_system_prompt,
}


def main():
    parser = argparse.ArgumentParser(description="dsh-super-injector Hook Handler")
    parser.add_argument("--event", required=True, choices=list(_HANDLER_MAP.keys()))
    args = parser.parse_args()

    raw = sys.stdin.read() if not sys.stdin.isatty() else "{}"
    try:
        ctx = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        ctx = {}

    result = _HANDLER_MAP[args.event](ctx)
    if isinstance(result, str):
        print(result)


if __name__ == "__main__":
    main()
