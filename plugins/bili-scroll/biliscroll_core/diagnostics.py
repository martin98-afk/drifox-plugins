# -*- coding: utf-8 -*-
"""环境自检：工具（bili_status）与 UI 卡共用同一份检查逻辑。"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutTimeout
from loguru import logger

from pathlib import Path
from typing import Any, Dict, Optional

from .paths import PLUGIN_ROOT, plugin_data_root


def collect_status(app_data: Optional[str] = None) -> Dict[str, Any]:
    """返回环境与今日进度的检查结果 dict；UI 直接渲染，工具转 JSON。"""
    checks: Dict[str, Any] = {}
    root = plugin_data_root(app_data)
    checks["数据目录"] = str(root) if root else "不可用（能力池未就绪）"

    checks["自带依赖"] = _check_deps()
    checks["B站工具"] = _check_tools_registered()
    checks["扫码凭证"] = _check_credential(root)

    try:
        from .round_runner import load_settings
        from .store import DutyStore

        settings = load_settings()
        store = DutyStore()
        checks["今日已挑/配额"] = f"{store.count_picked_today()} / {settings.get('daily_quota', 0)}"
        if settings.get("auto_comment"):
            checks["自动评论"] = f"开（UID: {settings.get('my_uid') or '未填'}，投递 {settings.get('delivery', 'comment')}）"
        else:
            checks["自动评论"] = "关"
        auto = ("午间 " if settings.get("peak_noon") else "") + ("夜间" if settings.get("peak_night") else "")
        checks["自动跑"] = auto.strip() or "关（只手动）"
        checks["最近判重"] = store.seen_recent(limit=8)
    except Exception as e:
        checks["配置"] = f"读取失败：{type(e).__name__}: {e}"

    return checks


def _check_deps() -> str:
    """deps/ 就绪检查：关键包试探（bilibili_api / mcp / qrcode / PIL / aiohttp）。"""
    missing = []
    for mod in ("bilibili_api", "mcp", "qrcode", "PIL", "aiohttp"):
        try:
            __import__(mod)
        except Exception:
            missing.append(mod)
    if missing:
        return f"缺失 {', '.join(missing)}（deps/ 不完整或与本机 Python 不匹配，重装插件）"
    return "就绪（随插件自带）"



def _schemas_with_timeout(mgr, timeout: float = 5.0) -> Dict[str, Any]:
    """MCP 客户端未就绪时 get_tool_schemas_by_server 会长时间阻塞，这里限时。

    超时/失败统一返回空 dict，上层按「工具未就绪」给提示；
    卡住的后台线程留给宿主收尾，不在这里等待（等待会拖死调用方线程）。
    """
    started = time.monotonic()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bili-schema")
    future = executor.submit(mgr.get_tool_schemas_by_server)
    try:
        result = future.result(timeout=timeout) or {}
        logger.debug(f"[bili-scroll] MCP 工具表读取 {time.monotonic() - started:.2f}s")
        return result
    except _FutTimeout:
        logger.warning(f"[bili-scroll] MCP 工具表读取超时（>{timeout:.0f}s），按未就绪处理")
        return {}
    except Exception as e:  # noqa: BLE001 — 查询失败等同未就绪
        logger.warning(f"[bili-scroll] MCP 工具表读取失败：{type(e).__name__}: {e}")
        return {}
    finally:
        executor.shutdown(wait=False)


def _check_tools_registered() -> str:
    """B站工具注册状态：MCP 形态下查 MCPClientManager 里 bili server 的工具数。"""
    try:
        from app.plugins.capabilities.resolve import pool_for

        # MCP 工具不进 ToolRegistry；mcp.call 能力直接给 MCPClientManager（_TOOL surface）
        pool = pool_for(plugin="bili-scroll", surface="tool") or {}
        mgr = pool.get("mcp.call")
        if callable(mgr):
            mgr = mgr()
        schemas = _schemas_with_timeout(mgr).get("bili", [])
        if schemas:
            return f"MCP 已注入 {len(schemas)} 个 B站工具"
        return "未注入（MCP 未连接，检查 .mcp.json / 控制端点）"
    except Exception as e:
        return f"查询失败：{type(e).__name__}: {e}"


def _check_credential(root: Optional[Path]) -> str:
    # 实际落盘位置：plugin_data/bili-scroll/（patch ⑦，root 即该目录），旧插件 data/ 仅作回退
    import json as _json

    candidates = [
        root / "bili_credential.json" if root else None,
        Path(PLUGIN_ROOT) / "data" / "bili_credential.json",
    ]
    for cred in candidates:
        if cred and cred.is_file():
            try:
                data = _json.loads(cred.read_text(encoding="utf-8"))
            except Exception:
                return "存在但读不出（损坏，重新扫码登录即可恢复）"
            if data.get("sessdata") and data.get("bili_jct"):
                return "已存在（登录过）"
            return "存在但为空壳（改版假成功遗留，重新扫码登录即可）"
    return "不存在（未登录，对话里喊 bili_login 扫码）"
