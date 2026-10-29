# -*- coding: utf-8 -*-
"""环境自检：工具（bili_status）与 UI 卡共用同一份检查逻辑。"""
from __future__ import annotations

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


def _check_tools_registered() -> str:
    try:
        from biliscroll_core.schema_registry import TOOL_SCHEMAS

        n = len(TOOL_SCHEMAS)
        return f"已注册 {n} 个" if n else "未注册（插件工具加载异常）"
    except Exception as e:
        return f"查询失败：{type(e).__name__}: {e}"


def _check_credential(root: Optional[Path]) -> str:
    cred = Path(PLUGIN_ROOT) / "data" / "bili_credential.json"
    if root and cred.is_file():
        return "已存在（登录过）"
    return "不存在（未登录，对话里喊 bili_login 扫码）"
