#!/usr/bin/env python3
"""Security guidance hook — DriFox native。

对 AI 生成的代码做静态安全模式检查（PostToolUse 触发）：
- Edit/Write/MultiEdit 时基于正则/子串规则检查写入内容
- 命中 25+ 类漏洞模式（硬编码密钥、SQL 注入、XSS、不安全的反序列化等）
- 结果作为附加上下文注入，提醒 AI 修复或说明

原始 Claude Code 版还包含基于 LLM 的 diff 审查（Stop/提交时），
DriFox 版聚焦纯规则静态检查层，LLM 审查由 DriFox 主循环自然承担。
"""
import json
import re
import sys

try:
    from patterns import SECURITY_PATTERNS
except ImportError:
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from patterns import SECURITY_PATTERNS


def _extract_content(tool_name: str, tool_input: dict) -> str:
    """从工具输入抽取待检查内容。"""
    if tool_name == "Write":
        return tool_input.get("content", "")
    if tool_name == "Edit":
        return tool_input.get("new_string", "")
    if tool_name == "MultiEdit":
        edits = tool_input.get("edits", [])
        if edits:
            return " ".join(e.get("new_string", "") for e in edits)
    return ""


def _check_patterns(file_path: str, content: str) -> list[tuple[str, str]]:
    """检查文件路径/内容是否命中安全模式，返回全部命中。"""
    normalized = file_path.lstrip("/")
    matches: list[tuple[str, str]] = []
    for pattern in SECURITY_PATTERNS:
        if "path_filter" in pattern:
            try:
                if not pattern["path_filter"](normalized):
                    continue
            except Exception:
                continue
        matched = False
        if "path_check" in pattern:
            try:
                if pattern["path_check"](normalized):
                    matched = True
            except Exception:
                pass
        if not matched and "substrings" in pattern and content:
            for sub in pattern["substrings"]:
                if sub in content:
                    matched = True
                    break
        if not matched and "regex" in pattern and content:
            try:
                if re.search(pattern["regex"], content):
                    matched = True
            except Exception:
                pass
        if matched:
            matches.append((pattern["ruleName"], pattern["reminder"]))
    return matches


def hook_post_tool_use(event: str, context: dict) -> str:
    """PostToolUse 钩子：检查写入内容的安全模式。"""
    tool_name = context.get("tool_name", "")
    if tool_name not in ("Write", "Edit", "MultiEdit"):
        return ""
    tool_input = context.get("tool_input") or context.get("message") or {}
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except json.JSONDecodeError:
            tool_input = {}
    content = _extract_content(tool_name, tool_input)
    if not content:
        return ""
    file_path = str(tool_input.get("file_path", "") or tool_input.get("file", "") or "")
    matches = _check_patterns(file_path, content)
    if not matches:
        return ""
    lines = [f"- **{name}**: {reminder}" for name, reminder in matches]
    return (
        "⚠️ Security Guidance 静态检查发现以下潜在安全问题，"
        "请修正或在不适用时明确说明原因：\n" + "\n".join(lines)
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    args = parser.parse_args()
    ctx = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {}
    handler = {"PostToolUse": hook_post_tool_use}.get(args.event)
    if handler:
        out = handler(args.event, ctx)
        if out:
            print(out)