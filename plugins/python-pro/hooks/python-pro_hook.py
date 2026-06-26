#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
python-pro Hook Handler

在 PostToolUse 时自动对 .py 文件运行 ruff check，检测代码风格和语法问题。
结果记录到 memory/python-pro.log。

使用方式（由 hooks.json 自动调用）：
    python python-pro_hook.py --event=PostToolUse

上下文数据通过 stdin (JSON) 传入，包含：
    - event_name: 事件名
    - tool_name: 工具名（如 write / edit / multi_edit）
    - file: 操作文件路径
    - project_root: 项目根目录
    - message: 工具调用参数摘要
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PLUGIN_NAME = "python-pro"
LOG_FILENAME = "python-pro.log"


# ============================================================
# 工具函数
# ============================================================


def get_project_root(ctx: dict) -> Path:
    """从上下文获取项目根目录。"""
    root = ctx.get("project_root", "")
    if root:
        return Path(root)
    return Path.cwd()


def append_log(project_root: Path, line: str) -> None:
    """追加一行到 memory/python-pro.log。"""
    log_dir = project_root / "memory"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / LOG_FILENAME
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()}  {line}\n")


def is_python_file(file_path: str) -> bool:
    """判断文件是否以 .py 结尾。"""
    return file_path.endswith(".py")


def is_write_tool(tool_name: str) -> bool:
    """判断工具是否为写操作工具。"""
    return tool_name in ("write", "edit", "multi_edit")


def run_ruff_check(file_path: Path) -> tuple[bool, str]:
    """
    运行 ruff check 检查指定文件。

    Returns:
        (success, output): success=True 表示 ruff 可用且无错误，output 为检查结果
    """
    try:
        result = subprocess.run(
            ["ruff", "check", str(file_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # ruff exit code: 0=无问题, 1=有 lint 错误, 2=内部错误
        if result.returncode == 0:
            return True, ""
        else:
            return False, result.stdout + result.stderr
    except FileNotFoundError:
        # ruff 未安装
        return False, "[ruff not installed] 请运行: pip install ruff"
    except subprocess.TimeoutExpired:
        return False, "[timeout] ruff check 超时（30s）"
    except Exception as e:
        return False, f"[error] {e}"


# ============================================================
# 事件处理函数
# ============================================================


def handle_post_tool_use(ctx: dict) -> None:
    """处理 PostToolUse 事件：检查 write/edit .py 文件后的 ruff 结果。"""
    tool_name = ctx.get("tool_name", "")
    file_path = ctx.get("file", "")

    # 只处理写操作工具 + Python 文件
    if not is_write_tool(tool_name) or not is_python_file(file_path):
        return

    project_root = get_project_root(ctx)
    file_abs = (project_root / file_path).resolve()

    if not file_abs.exists():
        return

    success, output = run_ruff_check(file_abs)

    if success:
        # 无 lint 问题，静默记录
        append_log(project_root, f"[OK] {file_path}")
    else:
        # 有问题或 ruff 未安装
        msg = f"[ruff] {file_path}"
        if output:
            msg += f"\n{output}"
        append_log(project_root, msg)


# ============================================================
# 钩子适配函数（由 hooks.json 调用）
# ============================================================


def hook_post_tool_use(ctx: dict) -> None:
    """PostToolUse 钩子入口。"""
    handle_post_tool_use(ctx)


# ============================================================
# CLI 入口（调试用）
# ============================================================


def main() -> None:
    parser = argparse.ArgumentParser(description="python-pro hook handler")
    parser.add_argument("--event", required=True, help="事件名")
    args = parser.parse_args()

    ctx = json.load(sys.stdin)
    if ctx.get("event_name") != args.event:
        sys.stderr.write(f"事件不匹配: expected={args.event}, got={ctx.get('event_name')}\n")
        sys.exit(1)

    if args.event == "PostToolUse":
        hook_post_tool_use(ctx)
    else:
        sys.stderr.write(f"未知事件: {args.event}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()