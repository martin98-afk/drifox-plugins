# -*- coding: utf-8 -*-
"""bili_status：环境自检（venv / MCP 连接 / 凭证 / 配置摘要 / 今日进度）。"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

# 宿主 tools 加载器不注插件根，先自注入再 import 本插件包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.tools.result import ToolResult


def _status_impl(tool_ctx, **_) -> ToolResult:
    app_data = (tool_ctx or {}).get("env", {}).get("app_data_dir")
    try:
        # biliscroll_core.* 热重载滞留旧版（宿主只清 _plugin_tool_* 与 ui 前缀）；
        # diagnostics 无跨轮状态，reload 自愈保证自检口径与磁盘一致
        import biliscroll_core.diagnostics as _diag

        importlib.reload(_diag)
        checks = _diag.collect_status(app_data)
    except Exception as e:
        return ToolResult(False, error=f"自检失败：{type(e).__name__}: {e}")
    return ToolResult(True, content=json.dumps(checks, ensure_ascii=False, indent=1, default=str))


def register(registry):
    registry.register(
        "bili_status",
        {"type": "function", "function": {
            "name": "bili_status",
            "description": "检查 bili-scroll 环境自检：控制端点、MCP 工具注入、登录凭证、配置与今日值班进度",
            "parameters": {"type": "object", "properties": {}, "required": []}},
        },
        impl=_status_impl,
        danger="safe",
        icon="bili",
        cn_name="B站值班·自检",
        group="B站值班",
        description="检查值班环境与今日进度",
    )
