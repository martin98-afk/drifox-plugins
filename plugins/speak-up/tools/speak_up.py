# -*- coding: utf-8 -*-
"""speak-up 工具 — 让模型（或设置卡的 action 按钮）直接掷骰 / 查状态。

不声明为 `dangerous`：掷骰不花钱，真发也只是往当前会话塞一条自己的念头，
风险等同用户自己打字。真发前仍受总开关与试运行约束之外的人工确认——
调用方显式传 action="roll_real" 才真发，不会误触。
"""

from __future__ import annotations

import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from loguru import logger  # noqa: E402

from app.tools.result import ToolResult  # noqa: E402

GROUP = "主动搭话"

_SCHEMA = {
    "type": "function",
    "function": {
        "name": "speak_up",
        "description": (
            "主动搭话的掷骰器。action=dry 只演练（不发送、记账后返回），"
            "action=real 真的往当前会话发一句自己的念头，action=status 查当前状态与最近记账。"
            "平时由插件自己的定时器调用，用户也可手动触发。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["dry", "real", "status"],
                    "description": "dry=演练（默认）/ real=真发 / status=查状态",
                },
            },
            "required": ["action"],
        },
    },
}


def _runner():
    """取全局单例 runner（实体在 speakup_core.runtime，同一进程只有一份）。"""
    from speakup_core.runtime import get_runner  # type: ignore

    return get_runner()


def _speak_up_impl(tool_ctx, **kwargs):
    action = str(kwargs.get("action") or "dry").strip().lower()
    try:
        runner = _runner()
    except Exception as e:  # noqa: BLE001 - UI 未加载时工具也不该崩
        return ToolResult(False, error=f"speak-up 运行时不可用：{e}")

    try:
        if action == "status":
            snap = runner.state_snapshot()
            entries = runner.recent_entries()
            lines = [
                f"运行中：{'是' if snap['running'] else '否'}",
                f"间隔：{snap['interval_seconds'] // 60} 分钟",
                f"连没中：{snap['misses']} 次",
            ]
            if snap["last_self_spoke"] > 0:
                import time

                cooled = (time.time() - snap["last_self_spoke"]) / 60.0
                lines.append(f"上次自己开口：{cooled:.1f} 分钟前")
            else:
                lines.append("上次自己开口：还没开过口")
            lines.append("")
            lines.append("最近记账：")
            for entry in entries[-15:]:
                lines.append(f"  {entry.at}  {entry.text}")
            return ToolResult(True, content="\n".join(lines))

        mode = "真发" if action == "real" else "演练"
        result = runner.roll(source="手动", mode=mode)
        return ToolResult(True, content=result["text"])
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[speak-up] 工具执行异常: {e}")
        return ToolResult(False, error=f"speak-up 执行失败：{e}")


def _preview(tool_args: dict) -> str:
    action = str(tool_args.get("action") or "dry")
    label = {"dry": "演练一次", "real": "真发一次", "status": "查看状态"}.get(action, action)
    return f"主动搭话 · {label}"


def register(registry):
    registry.register(
        "speak_up",
        _SCHEMA,
        impl=_speak_up_impl,
        danger="safe",
        icon="speak_up",
        cn_name="主动搭话",
        group=GROUP,
        description="按命中线掷骰决定要不要自己先开口",
        preview=_preview,
        render_mode="inline",
    )
