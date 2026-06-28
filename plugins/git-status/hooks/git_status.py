# -*- coding: utf-8 -*-
"""
PreUserMessage Hook — 向 LLM 上下文注入当前 Git 仓库状态

设计原则：
    1. 快速失败：非 git 仓库 / git 未安装 → 直接返回空字符串
    2. 超时保护：单次 git 命令最多 3s，避免卡死对话
    3. 长度限制：注入内容 ≤ 2000 字符，防止撑爆上下文
    4. 优雅降级：任何异常都返回部分信息或空，不抛错中断流程

收集的信息：
    - 当前分支（detached HEAD 时提示）
    - 相对 upstream 的 ahead/behind 提交数
    - 已暂存 / 未暂存 / 未跟踪 文件清单
    - 工作区 diff --shortstat 统计
    - 最近 5 条 commit（单行格式）

依赖：仅依赖系统已安装的 git 命令（无需 Python 第三方包）
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

PLUGIN_NAME = "git-status"

# 单次 git 命令超时（秒）。git 不应该慢，超过这个时间一律放弃
GIT_TIMEOUT = 3

# 注入上下文的最大字符数。超过则截断，避免撑爆 token
MAX_CONTEXT_LENGTH = 2000

# 列表项截断阈值：超过这个数量就折叠显示
_MAX_STAGED_ITEMS = 30
_MAX_UNSTAGED_ITEMS = 30
_MAX_UNTRACKED_ITEMS = 20
_MAX_RECENT_COMMITS = 5


# ============================================================
# 底层工具
# ============================================================


def _run_git(cwd: str, *args: str) -> tuple[str, str, int]:
    """执行 git 命令并返回 (stdout, stderr, returncode)

    统一封装错误处理，所有异常都被捕获并转为返回码 -1。
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT,
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        logger.warning(f"[{PLUGIN_NAME}] git {' '.join(args)} 超时（>{GIT_TIMEOUT}s）")
        return "", "timeout", -1
    except FileNotFoundError:
        # git 命令不存在
        return "", "git not found", -1
    except Exception as e:
        logger.error(f"[{PLUGIN_NAME}] git 执行异常: {e}")
        return "", str(e), -1


def _is_git_repo(cwd: str) -> bool:
    """检查目录是否在 Git 仓库中（含子目录）"""
    if not cwd:
        return False
    path = Path(cwd)
    if not path.exists() or not path.is_dir():
        return False
    _, _, code = _run_git(cwd, "rev-parse", "--is-inside-work-tree")
    return code == 0


# ============================================================
# 信息收集
# ============================================================


def _collect_branch_info(cwd: str) -> dict[str, Any]:
    """收集分支名 + ahead/behind 提交数"""
    info: dict[str, Any] = {"branch": "", "ahead": 0, "behind": 0}

    stdout, _, code = _run_git(cwd, "branch", "--show-current")
    if code == 0 and stdout:
        info["branch"] = stdout
    else:
        # detached HEAD 场景
        stdout, _, code = _run_git(cwd, "rev-parse", "--short", "HEAD")
        if code == 0 and stdout:
            info["branch"] = f"(detached @ {stdout})"

    # upstream 不存在时这条命令会失败，属正常情况，吞掉即可
    stdout, _, code = _run_git(
        cwd,
        "rev-list",
        "--left-right",
        "--count",
        "HEAD...@{u}",
    )
    if code == 0 and stdout:
        parts = stdout.split()
        if len(parts) == 2:
            try:
                info["ahead"] = int(parts[0])
                info["behind"] = int(parts[1])
            except ValueError:
                pass

    return info


def _collect_file_status(cwd: str) -> dict[str, list]:
    """收集工作树文件状态（porcelain v1，可机器解析）"""
    status = {"staged": [], "unstaged": [], "untracked": []}

    # porcelain v1 格式：每行 `XY filename` (X=staged, Y=unstaged)
    # -uall 把子目录里的 untracked 文件也展开显示
    stdout, _, code = _run_git(
        cwd,
        "status",
        "--porcelain=v1",
        "-uall",
        "--no-renames",  # 改名也按 add+delete 显示，避免路径前缀 R 老格式混淆
    )
    if code != 0 or not stdout:
        return status

    for line in stdout.splitlines():
        if len(line) < 3:
            continue
        x = line[0]   # 暂存区状态
        y = line[1]   # 工作区状态
        path = line[3:]

        if x == "?" and y == "?":
            # 未跟踪文件（仅工作区）
            status["untracked"].append(path)
        else:
            if x != " ":
                status["staged"].append((x, path))
            if y != " ":
                status["unstaged"].append((y, path))

    return status


def _collect_diff_stats(cwd: str) -> str:
    """工作区 diff --shortstat（一行摘要），空仓库时返回空串"""
    stdout, _, code = _run_git(cwd, "diff", "--shortstat")
    if code == 0:
        return stdout
    return ""


def _collect_recent_commits(cwd: str, n: int = _MAX_RECENT_COMMITS) -> list[str]:
    """最近 N 条 commit（短 hash + subject）"""
    stdout, _, code = _run_git(
        cwd,
        "log",
        f"-n{n}",
        "--pretty=format:%h %s",
    )
    if code == 0 and stdout:
        return stdout.splitlines()
    return []


# ============================================================
# 格式化输出
# ============================================================


_STATUS_CODE_DESC = {
    "M": "修改",
    "A": "新增",
    "D": "删除",
    "R": "改名",
    "C": "复制",
    "U": "未合并",
    "T": "类型变更",
}


def _describe_status(code: str) -> str:
    """将单字母状态码翻译为可读中文"""
    return _STATUS_CODE_DESC.get(code, code)


def _format_branch(info: dict[str, Any]) -> str:
    """格式化分支信息"""
    branch = info["branch"] or "(未知)"
    ahead = f" ↑{info['ahead']}" if info["ahead"] else ""
    behind = f" ↓{info['behind']}" if info["behind"] else ""
    return f"**当前分支**: `{branch}`{ahead}{behind}"


def _format_file_list(items: list, max_items: int, label: str) -> list[str]:
    """格式化文件状态列表（自动截断）"""
    if not items:
        return []

    lines = [f"- {label} ({len(items)}):"]
    shown, overflow = items[:max_items], max(0, len(items) - max_items)

    for entry in shown:
        if isinstance(entry, tuple):
            code, path = entry
            lines.append(f"  - [{_describe_status(code)}] `{path}`")
        else:
            lines.append(f"  - `{entry}`")

    if overflow:
        lines.append(f"  - ... 还有 {overflow} 项")
    return lines


def _format_status_section(files: dict[str, list]) -> list[str]:
    """格式化整个工作树状态段"""
    staged_lines = _format_file_list(files["staged"], _MAX_STAGED_ITEMS, "已暂存")
    unstaged_lines = _format_file_list(files["unstaged"], _MAX_UNSTAGED_ITEMS, "未暂存")
    untracked_lines = _format_file_list(files["untracked"], _MAX_UNTRACKED_ITEMS, "未跟踪")

    if not (staged_lines or unstaged_lines or untracked_lines):
        return ["**工作树状态**: 工作树干净，无未提交修改 ✓"]

    return ["**工作树状态**:"] + staged_lines + unstaged_lines + untracked_lines


def _format_recent_commits(commits: list[str]) -> str:
    """格式化最近 commits"""
    if not commits:
        return "**最近 commits**: (无)"
    lines = ["**最近 commits**:"]
    for commit in commits:
        lines.append(f"- `{commit}`")
    return "\n".join(lines)


# ============================================================
# Hook 入口
# ============================================================


def hook(event: str, context: dict) -> str:
    """PreUserMessage hook — 注入 Git 仓库状态到 LLM 上下文

    Args:
        event: 事件名（应为 PreUserMessage）
        context: backend 预取的上下文，含：
            - message: str 当前用户消息
            - project_root: str 当前窗口工作目录

    Returns:
        格式化的 Git 状态字符串。非 git 仓库 / git 未安装 / 任何异常
        时均返回空字符串，由 DriFox 视为"无注入"。
    """
    if event != "PreUserMessage":
        return ""

    cwd = context.get("project_root", "")
    if not cwd:
        return ""

    # 快速检查：不在 git 仓库直接返回，不浪费任何 git 调用
    if not _is_git_repo(cwd):
        return ""

    # 收集信息（每个收集函数独立处理失败，整体仍可继续）
    branch_info = _collect_branch_info(cwd)
    files = _collect_file_status(cwd)
    diff_stats = _collect_diff_stats(cwd)
    commits = _collect_recent_commits(cwd)

    # 拼装
    parts: list[str] = ["## Git 仓库状态", _format_branch(branch_info)]
    parts.extend(_format_status_section(files))

    if diff_stats:
        parts.append(f"\n**变更统计**: {diff_stats}")

    parts.append("")
    parts.append(_format_recent_commits(commits))

    result = "\n".join(parts)

    # 长度保护：超过上限直接截断
    if len(result) > MAX_CONTEXT_LENGTH:
        result = result[:MAX_CONTEXT_LENGTH] + "\n\n...(内容过长已截断)"

    logger.debug(f"[{PLUGIN_NAME}] 注入 Git 状态 ({len(result)} 字符)")
    return result
