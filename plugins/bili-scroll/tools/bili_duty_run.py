# -*- coding: utf-8 -*-
"""bili_duty_run：手动触发一轮值班（后台线程跑，立即返回）。

轮驱动与互斥都在 biliscroll_core.round_runner（工具与 UI 卡共用同一锁）；
完成/失败经 ui.notify 提醒，报告落盘 plugin_data。
"""
from __future__ import annotations

import threading
from typing import Any, Dict

from app.tools.result import ToolResult


def _notify_done(result: Dict[str, Any]) -> None:
    try:
        from app.plugins.capabilities.resolve import caps_for

        notify = caps_for("ui.notify", plugin="bili-scroll", surface="ui")
        if notify is None:
            return
        status = result.get("status")
        if status == "success":
            notify(f"值班轮完成，日报已写 {result.get('report_path', '')}", msg_type="success", duration=6000)
        elif status == "busy":
            pass  # 已有轮在跑，不打扰
        else:
            detail = result.get("error") or status
            notify(f"值班轮未完成：{detail}", msg_type="warning", duration=8000)
    except Exception:
        pass


def _duty_run_impl(tool_ctx, **_) -> ToolResult:
    def _run():
        from biliscroll_core.round_runner import run_duty_round

        try:
            result = run_duty_round()
        except Exception as e:  # 顶层屏障：线程里炸了不能静默
            result = {"status": "error", "error": f"{type(e).__name__}: {e}", "text": ""}
        _notify_done(result)

    threading.Thread(target=_run, daemon=True, name="bili-duty-round").start()
    return ToolResult(True, content="值班轮已启动：搜视频→读字幕→写日报，完成后弹通知。"
                                    "期间可继续其他对话，本轮约 5-20 分钟")


def register(registry):
    registry.register(
        "bili_duty_run",
        {"type": "function", "function": {
            "name": "bili_duty_run",
            "description": "手动触发一轮 B站值班（后台跑）：按设置搜视频、读字幕判断、写日报。完成或失败会弹系统通知",
            "parameters": {"type": "object", "properties": {}, "required": []}},
        },
        impl=_duty_run_impl,
        danger="safe",
        icon="bili",
        cn_name="B站值班·跑一轮",
        group="B站值班",
        description="启动一轮 B站值班（消耗 token，约 5-20 分钟）",
    )
