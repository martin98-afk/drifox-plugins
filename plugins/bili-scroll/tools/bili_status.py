# -*- coding: utf-8 -*-
"""bili_status：环境自检（venv / MCP 连接 / 凭证 / 配置摘要 / 今日进度）。"""
from __future__ import annotations

import json

# 宿主 tools 加载器不注插件根，先自注入再 import 本插件包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.tools.result import ToolResult


def _status_impl(tool_ctx, **_) -> ToolResult:
    app_data = (tool_ctx or {}).get("env", {}).get("app_data_dir")
    try:
        from biliscroll_core.diagnostics import collect_status

        checks = collect_status(app_data)
    except Exception as e:
        return ToolResult(False, error=f"自检失败：{type(e).__name__}: {e}")
    return ToolResult(True, content=json.dumps(checks, ensure_ascii=False, indent=1, default=str))


def register(registry):
    registry.register(
        "bili_status",
        {"type": "function", "function": {
            "name": "bili_status",
            "description": "检查 bili-scroll 环境自检：venv、MCP 连接、登录凭证、配置与今日值班进度",
            "parameters": {"type": "object", "properties": {}, "required": []}},
        },
        impl=_status_impl,
        danger="safe",
        icon="bili",
        cn_name="B站值班·自检",
        group="B站值班",
        description="检查值班环境与今日进度",
    )
