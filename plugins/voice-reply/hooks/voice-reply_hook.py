#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Voice Reply Hook — 将 AI 回复转为语音播放

标准 Python 钩子形式（由 DriFox hooks.json 配置为 type=python）：
    function: voice-reply_hook:handle_post_assistant_message

依赖：pyttsx3（需单独安装，详见插件 README.md）

CLI 调试：
    echo '{"response":"hello"}' | python voice-reply_hook.py --event=PostAssistantMessage
"""

import argparse
import json
import sys

PLUGIN_NAME = "voice-reply"


# ============================================================
# 核心功能
# ============================================================


def speak(text: str) -> str:
    """使用 pyttsx3 播放语音

    Args:
        text: 要朗读的文本

    Returns:
        播放状态字符串
    """
    try:
        import pyttsx3
    except ImportError:
        return (
            "❌ 缺少依赖 pyttsx3，请运行: pip install pyttsx3\n"
            "   或参考插件 README.md 安装依赖"
        )

    try:
        engine = pyttsx3.init()

        # 设置语音（索引 0 通常是中文 Huihui）
        voices = engine.getProperty("voices")
        if voices:
            engine.setProperty("voice", voices[0].id)

        # 语速中等
        engine.setProperty("rate", 180)

        engine.say(text)
        engine.runAndWait()

        return f"🔊 已语音播报回复（{len(text)}字）"

    except Exception as e:
        return f"❌ 语音播报失败: {e}"


# ============================================================
# 钩子入口（DriFox HookManager 调用）
# ============================================================


def handle_post_assistant_message(ctx: dict) -> str:
    """处理 PostAssistantMessage 事件

    Args:
        ctx: DriFox 传入的上下文字典，包含：
            - response / assistant_response: AI 回复文本
            - project_root: 项目根目录

    Returns:
        播报状态字符串（可空）
    """
    response = ctx.get("response", "") or ctx.get("assistant_response", "")
    if not response:
        return ""

    text = response.strip()
    if len(text) < 3:
        return ""

    # 截断过长文本（避免 TTS 耗时太久）
    if len(text) > 1000:
        text = text[:1000] + "……"

    return speak(text)


# ============================================================
# CLI 入口（仅用于本地调试）
# ============================================================


def main():
    """CLI 主入口"""
    parser = argparse.ArgumentParser(
        description=f"{PLUGIN_NAME} - AI 回复语音播报 Hook"
    )
    parser.add_argument(
        "--event",
        required=True,
        help="事件名（如 PostAssistantMessage）",
    )
    args = parser.parse_args()

    # 从 stdin 读取上下文 JSON
    try:
        raw = sys.stdin.read()
        ctx = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        print(f"[{PLUGIN_NAME}] 错误: 无法解析 stdin JSON — {e}", file=sys.stderr)
        sys.exit(1)

    if args.event == "PostAssistantMessage":
        result = handle_post_assistant_message(ctx)
        if result:
            print(result)
    else:
        print(f"[{PLUGIN_NAME}] 未知事件: {args.event}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
