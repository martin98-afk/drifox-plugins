#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ecc DriFox hooks — 精选核心 hook 的 Python 重写版

从 upstream ECC (affaan-m/ECC) hooks/hooks.json 精选 5 个高价值 hook，
用纯 Python 重写，不依赖 node 运行时。语义与上游等价：

| hook                  | DriFox 事件      | matcher              | 行为                          |
|-----------------------|------------------|----------------------|-------------------------------|
| git_push_reminder     | PreToolUse       | Bash (git push)      | 推送前提醒审查                |
| commit_quality        | PreToolUse       | Bash (git commit)    | 预提交质量检查，可阻断 (exit2)|
| doc_file_warning      | PreToolUse       | Write                | 临时 .md/.txt 文件警告        |
| quality_gate          | PostToolUse      | Edit/Write/MultiEdit | 编辑后格式化/质量检查         |
| check_console_log     | Stop             | -                    | 检查已修改文件中的 console.log|

上游参考：https://github.com/affaan-m/ECC/tree/main/scripts/hooks
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ============================================================
# 常量（与上游对齐）
# ============================================================

# doc-file-warning: 已知临时文档文件名（仅大写，明文临时文件）
ADHOC_FILENAMES = re.compile(r"^(NOTES|TODO|SCRATCH|TEMP|DRAFT|BRAINSTORM|SPIKE|DEBUG|WIP)\.(md|txt)$")
# 结构化目录：这些目录下的临时名是刻意的，不警告
STRUCTURED_DIRS = re.compile(r"(^|/)(docs|\.claude|\.github|commands|skills|benchmarks|templates|\.history|memory)/")

# check-console-log: 排除文件（测试/配置/scripts 目录）
CONSOLE_EXCLUDED = re.compile(
    r"(\.test\.[jt]sx?$|\.spec\.[jt]sx?$|\.config\.[jt]s$|/(scripts|__tests__|__mocks__)/)"
)

# commit-quality: 可检查的扩展名
CHECKABLE_EXTS = (".js", ".jsx", ".ts", ".tsx", ".py", ".go", ".rs")
# commit-quality: 秘密检测模式（上游精简集）
SECRET_PATTERNS = [
    (re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}"), "Anthropic API key"),
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "OpenAI API key"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36}"), "GitHub PAT"),
    (re.compile(r"AKIA[A-Z0-9]{16}"), "AWS Access Key"),
    (re.compile(r"api[_-]?key\s*[=:]\s*['\"]([^'\"]+)['\"]", re.IGNORECASE), "API key"),
]
# 明显的非秘密占位值（全文匹配才豁免）
PLACEHOLDER_RE = re.compile(
    r"^(process\.env\.[A-Za-z0-9_]+|\$\{[^}]*\}|<[^<>]*>"
    r"|REPLACE_ME|CHANGE_?ME|YOUR[_-]?API[_-]?KEY|YOUR[_-]?KEY[_-]?HERE"
    r"|API[_-]?KEY|SECRET|TOKEN|KEY|TODO|TBD|FIXME|XXX+)$",
    re.IGNORECASE,
)
# 常规提交格式
CONVENTIONAL_COMMIT = re.compile(r"^(feat|fix|docs|style|refactor|test|chore|build|ci|perf|revert)(\(.+\))?:\s*.+")

# 语言 → 格式化工具（可执行文件或失效则跳过）
FORMATTERS = {
    ".py": ("ruff", ["format"]),
    ".go": ("gofmt", ["-w"]),
}

IS_WINDOWS = os.name == "nt"


# ============================================================
# 工具函数
# ============================================================

def _ctx_tool_input(context: dict) -> dict:
    """提取工具输入（tool_input），兼容字符串/字典。"""
    ti = context.get("tool_input") or context.get("args") or {}
    if isinstance(ti, str):
        try:
            ti = json.loads(ti)
        except json.JSONDecodeError:
            ti = {}
    return ti if isinstance(ti, dict) else {}


def _ctx_command(context: dict) -> str:
    """提取当前 bash 命令。"""
    return str(_ctx_tool_input(context).get("command", "") or "")


def _ctx_file_path(context: dict) -> str:
    """提取操作的文件路径。"""
    ti = _ctx_tool_input(context)
    return str(ti.get("file_path") or ti.get("file") or ti.get("path") or "")


def _project_root(context: dict) -> Path:
    root = context.get("project_root", "")
    return Path(root) if root else Path.cwd()


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess | None:
    """运行 git 命令，失败返回 None。"""
    try:
        return subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _is_temp_doc_warn(target: str) -> bool:
    """doc-file-warning：目标是否为可疑临时文档。"""
    normalized = target.replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1]
    if not basename.lower().endswith((".md", ".txt")):
        return False
    if not ADHOC_FILENAMES.match(basename):
        return False
    if STRUCTURED_DIRS.search(normalized):
        return False
    return True


def _find_issue(value: str) -> str | None:
    """判断捕获的神秘值是否为明显占位符。"""
    v = (value or "").strip()
    if not v or PLACEHOLDER_RE.match(v):
        return None
    return v


def _run_detector(cmd: str, tool: str, args: list[str], cwd: Path, timeout: int = 15) -> bool:
    """运行检测器，返回命令是否可用并能执行。"""
    try:
        subprocess.run([cmd, *args], cwd=str(cwd), capture_output=True, text=True,
                       timeout=timeout, encoding="utf-8", errors="replace")
        return True
    except (OSError, subprocess.SubprocessError):
        return False


# ============================================================
# Hook 1: git push 提醒（PreToolUse / Bash）
# ============================================================

def hook_git_push_reminder(event: str, context: dict) -> str:
    """git push 前提醒审查变更（仅提醒，不阻断）。"""
    cmd = _ctx_command(context)
    if not re.search(r"\bgit\s+push\b", cmd):
        return ""
    return (
        "[Hook] 推送前提醒：请先审查变更（git status / git diff）确认内容正确。\n"
        "[Hook] 继续推送（如需交互式审查可移除该 hook）。"
    )


# ============================================================
# Hook 2: 预提交质量检查（PreToolUse / Bash，可阻断）
# ============================================================

def hook_commit_quality(event: str, context: dict) -> str:
    """git commit 前质量检查：暂存文件 lint / console.log / debugger / 秘密 / 提交信息格式。

    DriFox 阻断约定：返回 JSON decision=block 时阻止工具执行（等价上游 exit 2）。
    """
    cmd = _ctx_command(context)
    if not re.search(r"\bgit\s+commit\b", cmd):
        return ""

    root = _project_root(context)
    issues: list[str] = []

    # 1. 秘密检测（历史暂存文件内容）
    staged = _run_git(["diff", "--cached", "--name-only", "--diff-filter=ACMR"], root)
    if staged and staged.returncode == 0:
        for fname in staged.stdout.splitlines():
            fname = fname.strip()
            if not fname:
                continue
            content = _run_git(["show", f":{fname}"], root)
            if content is None or content.returncode != 0:
                continue
            for line_no, line in enumerate(content.stdout.splitlines(), 1):
                for pattern, name in SECRET_PATTERNS:
                    m = pattern.search(line)
                    if m:
                        # 捕获组 1 存在时做占位符豁免
                        if m.lastindex and _find_issue(m.group(1)) is None:
                            continue
                        issues.append(f"[secret] {fname}:{line_no} — 疑似 {name} 泄漏")

    # 2. 提交信息格式（-m/--message）
    msg_match = re.search(r"(?:-m|--message)[=\s]+(?:\"((?:\\.|[^\"\\])*)\"|'((?:\\.|[^'\\])*)'|([^'\"]+?)\s*$)", cmd)
    if msg_match:
        message = msg_match.group(1) or msg_match.group(2) or msg_match.group(3)
        if not CONVENTIONAL_COMMIT.match(message):
            issues.append("[format] 提交信息不符合 Conventional Commits 格式（type(scope): description）")
        if len(message) > 72:
            issues.append(f"[length] 提交信息过长（{len(message)} 字符，上限 72）")

    if not issues:
        return ""

    block_msg = "🔒 [ecc] 预提交质量检查发现以下问题：\n" + "\n".join(issues) + \
        "\n\n请修复后重新提交；如确认无误，请说明理由后重试。"
    return json.dumps({"decision": "block", "output": block_msg}, ensure_ascii=False)


# ============================================================
# Hook 3: 临时文档文件警告（PreToolUse / Write）
# ============================================================

def hook_doc_file_warning(event: str, context: dict) -> str:
    """写入 NOTES.md / TODO.txt 等临时文档时提醒放入结构化目录。"""
    target = _ctx_file_path(context)
    if not _is_temp_doc_warn(target):
        return ""
    return (
        f"[Hook] 警告：{target} 是临时文档文件名（NOTES/TODO/SCRATCH 等）。\n"
        "[Hook] 建议放入 docs/、skills/ 等结构化目录；若为草稿请说明用途。"
    )


# ============================================================
# Hook 4: 编辑后质量门（PostToolUse / Edit|Write|MultiEdit）
# ============================================================

def hook_quality_gate(event: str, context: dict) -> str:
    """编辑后对 .py/.go 文件运行格式化检查（ruff/gofmt，可用时才执行）。"""
    file_path = _ctx_file_path(context)
    if not file_path:
        return ""
    p = Path(file_path)
    ext = p.suffix.lower()
    if ext not in FORMATTERS:
        return ""
    if not p.exists():
        return ""

    tool, args = FORMATTERS[ext]
    results: list[str] = []
    if ext == ".py":
        proc = subprocess.run(
            [tool, "format", "--check", str(p)], cwd=str(_project_root(context)),
            capture_output=True, text=True, timeout=20, encoding="utf-8", errors="replace",
        )
        if proc.returncode not in (0,):
            results.append(f"[QualityGate] ruff format --check 未通过: {file_path}")
    elif ext == ".go":
        proc = subprocess.run(
            [tool, "-l", str(p)], cwd=str(_project_root(context)),
            capture_output=True, text=True, timeout=20, encoding="utf-8", errors="replace",
        )
        if proc.returncode == 0 and proc.stdout and proc.stdout.strip():
            results.append(f"[QualityGate] gofmt 需要格式化: {file_path}")

    if not results:
        return ""
    return "\n".join(results) + "\n[QualityGate] 建议运行格式化工具修复后提交。"


# ============================================================
# Hook 5: console.log 检查（Stop）
# ============================================================

def hook_check_console_log(event: str, context: dict) -> str:
    """回复结束后检查工作区已修改 JS/TS 文件中的 console.log。"""
    root = _project_root(context)
    git_root_proc = _run_git(["rev-parse", "--show-toplevel"], root)
    if git_root_proc is None or git_root_proc.returncode != 0:
        return ""
    git_root = Path(git_root_proc.stdout.strip())
    if not git_root.is_dir():
        return ""

    files_proc = _run_git(["diff", "--name-only", "--diff-filter=ACMR", "HEAD"], git_root)
    if files_proc is None or files_proc.returncode != 0:
        # 无 HEAD（新仓库）：退回工作区全部改动
        files_proc = _run_git(["diff", "--cached", "--name-only"], git_root)
        if files_proc is None:
            return ""
    target_files = [
        f for f in files_proc.stdout.splitlines()
        if f.strip() and f.endswith((".ts", ".tsx", ".js", ".jsx"))
        and not CONSOLE_EXCLUDED.search(f)
        and (git_root / f).exists()
    ]
    if not target_files:
        return ""

    hits = []
    for f in target_files:
        try:
            content = (git_root / f).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "console.log" in content:
            hits.append(f)

    if not hits:
        return ""
    return (
        "[Hook] 以下文件包含 console.log（提交前请移除）：\n"
        + "\n".join(f"  - {f}" for f in hits)
    )


# ============================================================
# CLI 调试入口
# ============================================================

_HANDLERS = {
    "git-push-reminder": hook_git_push_reminder,
    "commit-quality": hook_commit_quality,
    "doc-file-warning": hook_doc_file_warning,
    "quality-gate": hook_quality_gate,
    "console-log": hook_check_console_log,
}


def main() -> None:
    """CLI 调试：echo '{"tool_input":{"command":"git push"}}' | python ecc_hook.py --hook git-push-reminder"""
    import argparse

    parser = argparse.ArgumentParser(description="ecc hook 调试入口")
    parser.add_argument("--hook", required=True, choices=list(_HANDLERS))
    parser.add_argument("--event", default="PreToolUse")
    args = parser.parse_args()
    try:
        raw = sys.stdin.read()
        ctx = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        ctx = {}
    result = _HANDLERS[args.hook](args.event, ctx)
    if result:
        print(result)


if __name__ == "__main__":
    main()