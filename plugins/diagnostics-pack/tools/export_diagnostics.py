# -*- coding: utf-8 -*-
"""工具：导出诊断包。

给 AI 一个可调用的诊断入口。真正干活的是插件根下的 ``drifox_diag_pack``
（纯标准库），这里只负责解析数据目录、收参数、把结果转成 ToolResult。
"""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

PLUGIN_NAME = "diagnostics-pack"

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))


def _fmt_size(num: int) -> str:
    if num >= 1024 ** 2:
        return f"{num / 1024 ** 2:.1f} MB"
    return f"{max(1, num // 1024)} KB"


def _impl(tool_ctx=None, **kwargs):
    from app.plugins.sdk import ToolResult

    from drifox_diag_pack import build_pack
    from drifox_diag_pack.host_env import resolve_data_dir

    include_dumps = bool(kwargs.get("include_crash_dumps", True))
    try:
        max_mb = int(kwargs.get("max_mb", 50) or 50)
    except (TypeError, ValueError):
        max_mb = 50
    note = str(kwargs.get("note", "") or "")

    try:
        result = build_pack(
            resolve_data_dir("tool"),
            include_crash_dumps=include_dumps,
            max_mb=max_mb,
            note=note,
        )
    except Exception as exc:  # noqa: BLE001 — 打包失败要如实回给模型
        logger.exception(f"[diagnostics-pack] 导出失败: {exc}")
        return ToolResult(False, error=f"诊断包导出失败: {exc}")

    lines = [
        "诊断包已生成。",
        f"路径: {result['path']}",
        f"体积: {_fmt_size(result['size'])}（未压缩 {_fmt_size(result['uncompressed'])}，"
        f"{result['entries']} 个条目）",
        f"脱敏命中: {result['masked_hits']} 处",
        f"耗时: {result['duration_ms']} ms",
    ]
    if result["skipped"]:
        lines.append("未打包: " + "；".join(result["skipped"][:5]))
    if result["warnings"]:
        lines.append("提示: " + "；".join(result["warnings"][:5]))
    lines.append("注意: 包内含本机路径与日志片段，公开上传前先检查。")

    return ToolResult(
        True,
        content="\n".join(lines),
        artifacts=[
            {
                "path": result["path"],
                "kind": "file",
                "caption": "诊断包（日志+崩溃现场+脱敏配置）",
            }
        ],
        data={"diagnostics_pack": {key: result[key] for key in ("path", "size", "entries", "masked_hits")}},
    )


def register(registry) -> None:
    registry.register(
        "export_diagnostics",
        {
            "type": "function",
            "function": {
                "name": "export_diagnostics",
                "description": (
                    "把本机 DriFox 诊断信息打包成 zip：最近日志、错误摘要、崩溃堆栈与 minidump、"
                    "系统信息、插件清单、脱敏后的配置。用于排查崩溃、插件加载失败、卡顿等异常。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "include_crash_dumps": {
                            "type": "boolean",
                            "description": "是否包含 minidump（体积大，可能含内存片段），默认 true",
                        },
                        "max_mb": {
                            "type": "integer",
                            "description": "未压缩体积预算（MB），默认 50，范围 5-1000",
                        },
                        "note": {
                            "type": "string",
                            "description": "可选备注，写进包内 README，例如复现步骤或观察到的现象",
                        },
                    },
                },
            },
        },
        impl=_impl,
        danger="safe",
        icon="diagnostics",
        cn_name="导出诊断包",
        group="系统诊断",
        description="打包日志/崩溃现场/配置（脱敏）为 zip",
        aliases=["DiagnosticsPack", "ExportDiagnostics"],
    )
