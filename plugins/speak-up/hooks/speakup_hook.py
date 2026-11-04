# -*- coding: utf-8 -*-
"""speak-up hook — 记录用户发消息的精确时刻，供时机因子使用。

为什么需要它：`session.read()` 的消息带 `ts_ms`（毫秒），但只有在消息落盘后
才能读到；用户刚说完话的那几十秒里，插件若去读会话可能还看不到最新一条。
hook 在消息进会话的同一刻打点，精度和时效都更好。

拿不到 runner（UI 未加载）时静默跳过，不抛异常——hook 抛错会污染对话流程。
"""

from __future__ import annotations

import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from loguru import logger  # noqa: E402


def on_user_message(ctx):
    """用户发送消息后触发（PostUserMessage）。"""
    try:
        from ui.speakup_ui import get_runner  # type: ignore

        get_runner().note_user_activity()
    except Exception as e:  # noqa: BLE001 - hook 绝不能影响对话
        logger.debug(f"[speak-up] hook 记录用户活动失败: {e}")
