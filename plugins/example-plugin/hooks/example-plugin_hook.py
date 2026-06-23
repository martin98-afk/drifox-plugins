#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
example-plugin Hook Handler

最小参考实现：在 SessionStart 时写入一行日志，在 PostToolUse 时记录工具名。
仅作为钩子编写规范的演示，不要在生产中使用。
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


PLUGIN_NAME = "example-plugin"
LOG_FILENAME = "example-plugin.log"


# ============================================================
# 工具函数
# ============================================================


def get_project_root(ctx: dict) -> Path:
    root = ctx.get("project_root", "")
    if root:
        return Path(root)
    return Path.cwd()


def append_log(project_root: Path, line: str) -> None:
    """追加一行到 memory/example-plugin.log。"""
    log_dir = project_root / "memory"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / LOG_FILENAME
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} {line}\n")


# ============================================================
# 事件处理器
# ============================================================


def handle_session_start(ctx: dict) -> None:
    """SessionStart: 写入一行初始化日志。"""
    project_root = get_project_root(ctx)
    append_log(project_root, f"[SessionStart] plugin={PLUGIN_NAME} project={project_root}")


def handle_post_tool_use(ctx: dict) -> None:
    """PostToolUse: 记录工具名。"""
    project_root = get_project_root(ctx)
    tool_name = ctx.get("tool_name", "unknown")
    file_path = ctx.get("file", "")
    append_log(project_root, f"[PostToolUse] tool={tool_name} file={file_path}")


# ============================================================
# Python Hook 适配函数（供 hooks.json 派发）
# 签名: (event: str, context: dict) -> str | None
# ============================================================


def hook_session_start(event: str, context: dict):
    handle_session_start(context)
    return "ok"


def hook_post_tool_use(event: str, context: dict):
    handle_post_tool_use(context)
    return "ok"


# ============================================================
# CLI 入口（独立调试用）
# 用法:
#   echo '{}' | python example-plugin_hook.py --event=SessionStart
# ============================================================


_HANDLER_MAP = {
    "SessionStart": handle_session_start,
    "PostToolUse": handle_post_tool_use,
}


def main():
    parser = argparse.ArgumentParser(description="example-plugin Hook Handler")
    parser.add_argument("--event", required=True, choices=list(_HANDLER_MAP.keys()))
    args = parser.parse_args()

    raw = sys.stdin.read() if not sys.stdin.isatty() else "{}"
    try:
        ctx = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        ctx = {}

    handler = _HANDLER_MAP[args.event]
    handler(ctx)


if __name__ == "__main__":
    main()
