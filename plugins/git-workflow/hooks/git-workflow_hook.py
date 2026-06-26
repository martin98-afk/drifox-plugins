#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
git-workflow Hook Handler

在 PreToolUse 事件中拦截 `git commit` 命令，检查提交消息是否符合
Conventional Commits 规范。如果不符合，输出警告提示。

使用方式（由 hooks.json 自动调用）：
    python git-workflow_hook.py --event=PreToolUse

上下文数据通过 stdin (JSON) 传入，包含：
    - event_name: 事件名
    - tool_name: 工具名（PreToolUse 时为 "bash" 等）
    - message: 工具调用参数
    - project_root: 项目根目录
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


# ============================================================
# 常量
# ============================================================

PLUGIN_NAME = "git-workflow"

# Conventional Commits 正则表达式
# 格式: type(scope): description
# type: feat, fix, docs, style, refactor, perf, test, chore, ci, revert
# scope: 可选，小写字母和连字符
# description: 小写字母开头，不超过72字符
CC_PATTERN = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|chore|ci|revert)"
    r"(\([a-z0-9/-]+\))?"  # 可选 scope
    r": "
    r"[a-z][a-z0-9 -]*"  # description，首字母小写
    r"{1,72}$"  # 长度限制
)

# 合法的 git commit 参数组合（用于从 message 中提取提交消息）
GIT_COMMIT_MSG_PATTERN = re.compile(
    r"git\s+commit(?:\s+-(?:m|message)\s+['\"](.+?)['\"]|\s+--message\s+['\"](.+?)['\"])?",
    re.IGNORECASE,
)


# ============================================================
# 工具函数
# ============================================================

def get_project_root(ctx: dict) -> Path:
    """获取项目根目录。"""
    root = ctx.get("project_root", "")
    if root:
        return Path(root)
    return Path.cwd()


def extract_commit_message(message: str) -> str | None:
    """从 bash 命令中提取 git commit 的提交消息。

    Args:
        message: bash 工具的 message 参数

    Returns:
        提取的提交消息，如果未找到返回 None
    """
    # 查找 git commit -m "xxx" 或 git commit --message "xxx" 形式
    match = GIT_COMMIT_MSG_PATTERN.search(message)
    if match:
        # group(1) 或 group(2) 是 -m 或 --message 的值
        return match.group(1) or match.group(2)

    # 如果没有 -m 参数但有 --amend，提示用户需要先 add
    if re.search(r"git\s+commit\s+--amend", message, re.IGNORECASE):
        # 检查是否有 -m（修改消息）还是 --no-edit（仅追加）
        if re.search(r"--no-edit", message, re.IGNORECASE):
            return "[amend] --no-edit"
        return "[amend]"

    return None


def validate_commit_message(msg: str) -> tuple[bool, str]:
    """验证提交消息是否符合 Conventional Commits 规范。

    Args:
        msg: 提交消息

    Returns:
        (是否合规, 错误信息)
    """
    if not msg or msg.startswith("[amend]"):
        # amend 模式不进行格式检查（可能是修改已有提交）
        return True, ""

    msg_stripped = msg.strip()

    if CC_PATTERN.match(msg_stripped):
        return True, ""

    # 详细错误诊断
    lines = msg_stripped.split("\n")
    first_line = lines[0] if lines else ""

    if not first_line:
        return False, "提交消息不能为空"

    # 检查 type
    type_match = re.match(r"^([a-z]+)", first_line)
    if not type_match:
        return False, f"提交消息必须以合法类型开头（feat、fix、docs 等），当前：'{first_line[:20]}...'"

    valid_types = ["feat", "fix", "docs", "style", "refactor", "perf", "test", "chore", "ci", "revert"]
    commit_type = type_match.group(1)
    if commit_type not in valid_types:
        return False, f"未知的提交类型 '{commit_type}'，必须是: {', '.join(valid_types)}"

    # 检查格式
    if ":" not in first_line:
        return False, f"提交消息必须包含 ': ' 分隔符，格式: type(scope): description"

    if not re.match(r"^[a-z]+(\([a-z0-9/-]+\))?:", first_line):
        return False, "格式错误。正确格式: type(scope): description（如 feat(auth): add login）"

    # 检查 description 首字母
    desc_part = first_line.split(":", 1)[1].strip()
    if desc_part and not desc_part[0].islower():
        return False, "description 首字母必须小写"

    # 检查长度
    if len(first_line) > 72:
        return False, f"第一行过长（{len(first_line)} 字符），应不超过 72 字符"

    return False, f"格式不符合 Conventional Commits 规范: '{first_line[:50]}...'"


def format_warning(commit_msg: str, error: str) -> str:
    """格式化警告消息。"""
    return (
        f"⚠️  [{PLUGIN_NAME}] 提交消息格式警告\n"
        f"\n"
        f"消息: {commit_msg[:50]}{'...' if len(commit_msg) > 50 else ''}\n"
        f"问题: {error}\n"
        f"\n"
        f"正确格式示例:\n"
        f"  feat(auth): add OAuth2 login\n"
        f"  fix(ui): correct button alignment\n"
        f"  docs: update README\n"
        f"\n"
        f"如需忽略此警告，请使用 --no-verify 参数临时绕过。"
    )


# ============================================================
# 处理器
# ============================================================

def handle_pre_tool_use(ctx: dict[str, Any]) -> dict[str, Any]:
    """PreToolUse 事件处理器。

    在 git commit 执行前检查提交消息格式。

    Args:
        ctx: DriFox 传入的上下文，包含 event_name, tool_name, message 等

    Returns:
        处理结果字典，包含警告信息
    """
    tool_name = ctx.get("tool_name", "")
    message = ctx.get("message", "")

    # 只处理 bash 工具
    if tool_name != "bash":
        return {"continue": True}

    # 检查是否是 git commit 命令
    if not re.search(r"git\s+commit", message, re.IGNORECASE):
        return {"continue": True}

    # 提取提交消息
    commit_msg = extract_commit_message(message)
    if commit_msg is None:
        # 可能是交互式提交，忽略
        return {"continue": True}

    # 验证提交消息
    is_valid, error = validate_commit_message(commit_msg)

    if is_valid:
        return {"continue": True}

    # 输出警告（不阻止执行，只是提示）
    warning = format_warning(commit_msg, error)
    print(warning, file=sys.stderr)

    return {"continue": True, "warning": warning}


# ============================================================
# Hook 适配器
# ============================================================

def hook_pre_tool_use() -> None:
    """PreToolUse 事件的 Hook 入口。

    从命令行参数解析上下文，调用处理器。
    """
    parser = argparse.ArgumentParser(description=f"{PLUGIN_NAME} - PreToolUse hook")
    parser.add_argument("--event", required=True, help="事件名")
    args = parser.parse_args()

    # 从 stdin 读取上下文
    try:
        ctx = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(f"[{PLUGIN_NAME}] 错误: 无法解析 stdin JSON", file=sys.stderr)
        sys.exit(1)

    result = handle_pre_tool_use(ctx)
    sys.exit(0 if result.get("continue", True) else 1)


# ============================================================
# CLI 入口
# ============================================================

def main() -> None:
    """CLI 主入口，支持直接调用测试。"""
    parser = argparse.ArgumentParser(description=f"{PLUGIN_NAME} hook CLI")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # pre-tool-use 子命令
    pre_parser = subparsers.add_parser("pre-tool-use", help="PreToolUse 事件处理")
    pre_parser.add_argument("--message", required=True, help="工具调用 message")

    args = parser.parse_args()

    if args.command == "pre-tool-use":
        ctx = {
            "event_name": "PreToolUse",
            "tool_name": "bash",
            "message": args.message,
            "project_root": str(Path.cwd()),
        }
        result = handle_pre_tool_use(ctx)
        if result.get("warning"):
            print(result["warning"])
        else:
            print("✅ 提交消息格式检查通过")
    else:
        # 默认调用 hook_pre_tool_use
        hook_pre_tool_use()


if __name__ == "__main__":
    main()