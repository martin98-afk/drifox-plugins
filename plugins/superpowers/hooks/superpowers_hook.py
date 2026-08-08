#!/usr/bin/env python3
"""Superpowers SessionStart hook — DriFox native。

在会话启动时把 using-superpowers/SKILL.md 内容注入上下文，让 AI
一开始就知道自己拥有 superpowers 技能库，知道如何检索和使用它们。
"""
import json
import os

_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_using_superpowers() -> str:
    """读取 using-superpowers SKILL.md 全文。"""
    path = os.path.join(_PLUGIN_ROOT, "skills", "using-superpowers", "SKILL.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def hook_session_start(event: str, context: dict) -> str:
    """SessionStart 钩子：注入 superpowers 使用指引。

    返回注入到上下文的文本；读取失败时返回空串，不阻塞会话。
    """
    content = _read_using_superpowers()
    if not content:
        return ""
    return (
        "<EXTREMELY_IMPORTANT>\n"
        "You have superpowers.\n\n"
        "**Below is the full content of your 'superpowers:using-superpowers' "
        "skill - your introduction to using skills. For all other skills, "
        "use the 'Skill' tool:**\n\n"
        f"{content}\n"
        "</EXTREMELY_IMPORTANT>"
    )


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    args = parser.parse_args()
    ctx = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {}
    handler = {"SessionStart": hook_session_start}.get(args.event)
    if handler:
        print(handler(args.event, ctx))