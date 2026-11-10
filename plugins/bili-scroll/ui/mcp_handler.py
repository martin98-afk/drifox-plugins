# -*- coding: utf-8 -*-
"""bili-scroll 的进程内 MCP handler。

工具表与实现来自 biliscroll_core.bili_impl（import 期已 _build() 完毕），
不再经 HTTP 自调用，也不 import mcp SDK；宿主 LocalMcpGateway 负责讲
Streamable HTTP 的 JSON-RPC 帧。

原先 control_server 的二维码弹窗副作用在此保留（bili_login 出码直显）。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from biliscroll_core import bili_impl

from .qrcode_popup import close_qrcode, show_qrcode


def build_tools() -> List[dict]:
    """把 OpenAI function schema 转成 MCP Tool 列表（工具表动态）。"""
    return [
        {
            "name": name,
            "description": schema["function"]["description"],
            "inputSchema": schema["function"]["parameters"],
        }
        for name, schema in sorted(bili_impl.SCHEMAS.items())
    ]


def _maybe_qrcode_popup(name: str, content: str) -> None:
    """扫码体验：bili_login 出码弹窗直显；登录 done/timeout 自动收窗。"""
    if not isinstance(content, str):
        return
    try:
        if name == "bili_login":
            data = json.loads(content)
            if data.get("status") == "qrcode_ready":
                img = data.get("qrcode_image") or ""
                if img.startswith("data:image"):
                    show_qrcode(img)
        elif name == "bili_login_check" and isinstance(content, str):
            if '"status": "done"' in content or '"status": "timeout"' in content:
                close_qrcode()
    except Exception as e:
        from loguru import logger

        logger.warning(f"[bili-scroll] 二维码弹窗处理失败: {e}")


def mcp_handle(params: Dict[str, Any]) -> dict:
    """gateway 回调：入参即 tools/call 的 params（name + arguments）-> {'text': str}。"""
    name = params.get("name") or ""
    kwargs = params.get("arguments") or {}
    impl = bili_impl.IMPLS.get(name)
    if impl is None:
        return {"text": f"未知工具: {name}", "isError": True}
    try:
        content = impl(**kwargs)
        _maybe_qrcode_popup(name, content)
        if isinstance(content, str):
            return {"text": content}
        if isinstance(content, list):
            return {"content": content}
        return {"text": json.dumps(content, ensure_ascii=False, default=str)}
    except Exception as e:
        from loguru import logger

        logger.warning(f"[bili-scroll] 工具调用失败: {type(e).__name__}: {e}")
        return {"text": f"{type(e).__name__}: {e}", "isError": True}
