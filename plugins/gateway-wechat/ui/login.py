# -*- coding: utf-8 -*-
"""微信 iLink 扫码登录核心流程（纯逻辑，无 Qt 依赖）。

流程（对应 iLink 官方接口，协议参考 openhanako wechat-login.ts，Apache-2.0）：
    fetch_qr()           GET /ilink/bot/get_bot_qrcode  → (qrcode_id, PNG 字节)
    poll_status(id)      GET /ilink/bot/get_qrcode_status（服务端 hold 35s）
    save_bot_token(tok)  写插件配置 + 重建网关（扫码后免重启）

二维码渲染走插件自包含的 deps/segno（零依赖纯 Python）。UI 层见 config_card.py。
"""

from __future__ import annotations

import io
import json
import os
import sys
import urllib.parse
from typing import Any, Dict, Tuple

from loguru import logger

LOGIN_BASE_URL = "https://ilinkai.weixin.qq.com"
BOT_TYPE = "3"
PLUGIN_NAME = "gateway-wechat"

# 服务端长轮询 hold 35s，读超时须大于它；connect 独立短超时
POLL_TIMEOUT = 45
GET_QR_TIMEOUT = 15

# segno 在插件 deps/（ui/ 的上一级）
_DEPS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "deps"))
if os.path.isdir(_DEPS) and _DEPS not in sys.path:
    sys.path.insert(0, _DEPS)


def _login_headers() -> Dict[str, str]:
    return {"iLink-App-ClientVersion": "1"}


def _http_get(url: str, timeout: int = POLL_TIMEOUT) -> Dict[str, Any]:
    """同步 GET（调用方在后台线程跑，阻塞可接受）。"""
    import httpx

    resp = httpx.get(
        url,
        headers=_login_headers(),
        timeout=httpx.Timeout(timeout, connect=10.0),
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def render_qr_png(qr_text: str, scale: int = 12) -> bytes:
    """segno 渲染二维码 PNG（scale 12 ≈ 540px 源，420px 展示仍清晰可扫）。"""
    import segno

    qr = segno.make(qr_text, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=scale, border=2)
    return buf.getvalue()


def fetch_qr() -> Tuple[str, bytes]:
    """取登录二维码，返回 (qrcode_id, PNG 字节)。失败抛异常。"""
    url = f"{LOGIN_BASE_URL}/ilink/bot/get_bot_qrcode?bot_type={BOT_TYPE}"
    data = _http_get(url, timeout=GET_QR_TIMEOUT)
    qr_content = data.get("qrcode_img_content") or data.get("qrcode")
    qrcode_id = data.get("qrcode")
    if not qr_content or not qrcode_id:
        raise RuntimeError(f"服务器未返回二维码: {json.dumps(data, ensure_ascii=False)[:200]}")
    return str(qrcode_id), render_qr_png(str(qr_content))


def poll_status(qrcode_id: str) -> Dict[str, Any]:
    """轮询扫码状态，返回服务端原始 dict（status/bot_token/ilink_bot_id…）。"""
    url = f"{LOGIN_BASE_URL}/ilink/bot/get_qrcode_status?qrcode={urllib.parse.quote(qrcode_id)}"
    return _http_get(url)


def save_bot_token(token: str) -> str:
    """confirmed 后写入配置并触发网关重建重连，返回给用户看的状态说明。"""
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    store = PluginConfigStore()
    store.set_values(PLUGIN_NAME, {"bot_token": token})
    try:
        if not bool(store.get(PLUGIN_NAME, "enabled")):
            logger.info("[wechat_login] token 已写入（网关未启用，开启开关后连接）")
            return "登录成功，token 已保存。打开上方开关即可连接。"
        from app.gateway.manager import get_platform_manager

        mgr = get_platform_manager()
        if mgr is None:
            logger.info("[wechat_login] token 已写入（网关管理器未初始化）")
            return "登录成功，token 已保存。网关启动后自动连接。"
        mgr.rebuild_plugin_platforms(PLUGIN_NAME, restart_if_running=True)
        logger.info("[wechat_login] token 已写入，网关已重建重连")
        return "登录成功，token 已保存，网关已重连。"
    except Exception as e:  # noqa: BLE001 — 重连失败不影响 token 落盘
        logger.warning(f"[wechat_login] 自动重连未触发（可手动开关启用）: {e}")
        return "登录成功，token 已保存。重连未触发，开关拨一次即可。"
