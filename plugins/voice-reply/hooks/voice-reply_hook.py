#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Voice Reply Hook — 将 AI 回复转为语音播放（Windows SAPI5，零第三方依赖）

执行机制：DriFox python 类型 hook，由 HookManager 在 DriFox 进程内
以 importlib 加载执行（function: .voice-reply_hook:handle_post_assistant_message）。

语音合成直接调用 Windows 自带 SAPI5 COM 接口（win32com / pywin32，
随 DriFox 运行环境自带），无需安装 pyttsx3 等任何额外依赖。

播放采用异步模式（SVSFlagsAsync），不阻塞聊天流程。

CLI 调试：
    echo {"response":"hello"} | python voice-reply_hook.py --event=PostAssistantMessage
"""

import argparse
import json
import sys
import threading

PLUGIN_NAME = "voice-reply"

# 播报文本上限（字），避免语音队列过长
MAX_TEXT_LEN = 500

# SAPI5 Speak 标志：SVSFlagsAsync = 1（异步播报，立即返回）
_SVSFlagsAsync = 1

# 每个线程独立的 SpVoice 引擎（hook 线程池线程常驻复用，对象长期存活保证播完）
_local = threading.local()


def _get_engine():
    """获取当前线程的 SAPI SpVoice 引擎（懒创建 + 线程级缓存）

    Returns:
        SpVoice COM 对象；初始化失败返回 None
    """
    engine = getattr(_local, "engine", None)
    if engine is not None:
        return engine

    try:
        import win32com.client
    except ImportError:
        return None

    try:
        engine = win32com.client.Dispatch("SAPI.SpVoice")

        # 优先选择中文语音（如 Microsoft Huihui）
        try:
            voices = engine.GetVoices()
            for i in range(voices.Count):
                if "Chinese" in voices.Item(i).GetDescription():
                    engine.Voice = voices.Item(i)
                    break
        except Exception:
            pass

        # 语速（SAPI 范围 -10 ~ 10，0 为正常）
        try:
            engine.Rate = 1
        except Exception:
            pass
        # 音量 0 ~ 100
        try:
            engine.Volume = 100
        except Exception:
            pass

        _local.engine = engine
        return engine
    except Exception:
        return None


# ============================================================
# 核心功能
# ============================================================


def speak(text: str) -> str:
    """使用 Windows SAPI5 异步播放语音

    Args:
        text: 要朗读的文本

    Returns:
        播放状态字符串
    """
    if sys.platform != "win32":
        return "❌ 语音播报仅支持 Windows（SAPI5）"

    engine = _get_engine()
    if engine is None:
        return "❌ 语音引擎初始化失败（win32com/SAPI5 不可用）"

    try:
        # 异步播报：立即返回，不阻塞聊天流程
        engine.Speak(text, _SVSFlagsAsync)
        return f"🔊 已开始语音播报（{len(text)}字）"
    except Exception as e:
        return f"❌ 语音播报失败: {e}"


# ============================================================
# 钩子入口（DriFox HookManager 调用）
# ============================================================


def handle_post_assistant_message(event: str = "", context: dict | None = None) -> str:
    """处理 PostAssistantMessage 事件（DriFox 约定签名 event, context）

    Args:
        event: 事件名
        context: DriFox 传入的上下文字典，包含：
            - response / assistant_response: AI 回复文本
            - project_root: 项目根目录

    Returns:
        播报状态字符串（可空）
    """
    ctx = context or {}
    response = ctx.get("response", "") or ctx.get("assistant_response", "")
    if not response:
        return ""

    text = response.strip()
    if len(text) < 3:
        return ""

    # 截断过长文本（避免语音队列过长）
    if len(text) > MAX_TEXT_LEN:
        text = text[:MAX_TEXT_LEN] + "……"

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
        result = handle_post_assistant_message(args.event, ctx)
        if result:
            print(result)
    else:
        print(f"[{PLUGIN_NAME}] 未知事件: {args.event}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
