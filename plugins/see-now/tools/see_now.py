# -*- coding: utf-8 -*-
"""see_now 工具 — 让模型按变化量看屏幕。

两个 action：

- `once`：立刻抓一帧返回（等同截图，但走同一条缩放/编码链，尺寸压到 800×450）
- `watch`：等攒够一帧有意义的画面再返回；模型思考期间采集继续，不空等

返回的图通过 `ToolResult.image_data`（协议 B）交给宿主视觉注入——
宿主 `chat_worker` 会把它塞进下一轮请求，模型就能直接看见。
`metadata={"provides_image": True}` 让宿主知道这个工具会产图。

采集循环来自 `seenow_core.loop`（本插件内单例，atexit 兜底），不依赖 ui 组件。
"""

from __future__ import annotations

import base64
import sys
import time
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from loguru import logger  # noqa: E402

from app.tools.result import ToolResult  # noqa: E402

GROUP = "看屏幕"

_SCHEMA = {
    "type": "function",
    "function": {
        "name": "see_now",
        "description": (
            "按「画面变化量」看屏幕：只把真正变化了的几帧拼成一张宫格图交给你，"
            "静止画面几乎不出图。action=once 立刻给一帧当前屏幕；"
            "action=watch 等这段时间里发生的变化（攒够变化帧或到兜底时间才返回）。"
            "适合「确认操作结果」「看看用户现在在做什么」。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["once", "watch"],
                    "description": "once=立刻一帧 / watch=等变化（默认 watch）",
                },
                "timeout": {
                    "type": "number",
                    "description": "watch 最长等多少秒（默认 30，上限 120）",
                },
                "say": {
                    "type": "string",
                    "description": "可选：附在结果里对用户说的一句话",
                },
            },
            "required": ["action"],
        },
    },
}


def _get_loop():
    from seenow_core.loop import get_loop  # type: ignore

    return get_loop()


def _see_now_impl(tool_ctx, **kwargs):
    action = str(kwargs.get("action") or "watch").strip().lower()
    say = str(kwargs.get("say") or "").strip()
    try:
        timeout = float(kwargs.get("timeout") or 30)
    except (TypeError, ValueError):
        timeout = 30.0
    timeout = max(5.0, min(120.0, timeout))

    from seenow_core.config import load_config  # type: ignore

    if not load_config().enabled:
        return ToolResult(False, error="看屏幕被关闭了（设置 → 插件 → 看屏幕 → 允许看屏幕）")

    try:
        loop = _get_loop()
    except Exception as e:  # noqa: BLE001 - 运行时未就绪时工具也不该崩
        return ToolResult(False, error=f"see-now 运行时不可用：{e}")

    if not loop.is_running() and not loop.start():
        return ToolResult(False, error="采集启动失败（取不到屏幕，检查屏幕录制权限）")

    try:
        if action == "once":
            sheet = loop.grab_once()
            if sheet is None:
                return ToolResult(False, error="抓屏失败（可能没有屏幕访问权限）")
        else:
            sheet = _watch(loop, timeout)
            if sheet is None:
                return ToolResult(
                    True,
                    content=(
                        f"{_say_prefix(say)}过去 {timeout:.0f} 秒画面没有明显变化。"
                        "（静止屏幕几乎不出图，这是预期的）"
                    ),
                )
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[see-now] 工具执行异常: {e}")
        return ToolResult(False, error=f"see_now 执行失败：{e}")

    b64 = base64.b64encode(sheet.png).decode("ascii")
    content = f"{_say_prefix(say)}{sheet.describe()}"
    return ToolResult(
        True,
        content=content,
        image_data={"mime": "image/png", "data": b64},
    )


def _say_prefix(say: str) -> str:
    return f"{say}\n\n" if say else ""


def _watch(loop, timeout: float):
    """等攒够帧再出图；超时返回 None（画面没变化）。

    每 0.25 秒取一次，同时刷新采集循环的活跃时间——watch 期间线程不会被空闲自停。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        sheet = loop.take(min_frames=1)
        if sheet is not None:
            return sheet
        time.sleep(0.25)
    # 最后一次机会：超时那一刻若刚好攒到帧，也给出去
    return loop.take(min_frames=1)


def _preview(tool_args: dict) -> str:
    action = str(tool_args.get("action") or "watch")
    if action == "once":
        return "看一眼当前屏幕"
    timeout = tool_args.get("timeout") or 30
    return f"看屏幕变化（最多等 {timeout} 秒）"


def register(registry):
    registry.register(
        "see_now",
        _SCHEMA,
        impl=_see_now_impl,
        danger="safe",
        icon="眼睛",
        cn_name="看屏幕",
        group=GROUP,
        description="按变化量看屏幕，只把变了的画面拼成一张图",
        preview=_preview,
        render_mode="expand",
        metadata={"provides_image": True},
    )
