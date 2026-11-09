# -*- coding: utf-8 -*-
"""钉钉设备注册扫码登录（官方设备注册 API，纯 HTTP 三步）。

协议对齐 dsh-im src/channels/dingtalk/device-auth.mjs（MIT）：
    POST {base}/app/registration/init    {"source": SOURCE}   → {nonce}
    POST {base}/app/registration/begin   {"nonce"}            → {device_code,
                                    verification_uri_complete, user_code, expires_in, interval}
    POST {base}/app/registration/poll    {"device_code"}      → {status, client_id,
                                    client_secret, fail_reason}
status ∈ WAITING / SUCCESS / FAIL / EXPIRED。

二维码内容 = verification_uri_complete（手机钉钉扫码后网页确认授权）。
凭据产出 = client_id + client_secret，即钉钉应用凭据，直接写插件配置。

SDK 延迟导入纪律：复用宿主 httpx；二维码渲染走插件自包含 deps/segno。
"""

from __future__ import annotations

import io
import os
import sys
from typing import Any, Dict, Tuple

from loguru import logger

REGISTRATION_BASE_URL = "https://oapi.dingtalk.com"
REGISTRATION_SOURCE = "DING_DWS_CLAW"
PLUGIN_NAME = "gateway-dingtalk"

# poll 为立即返回（非长轮询），调用方按 interval 节奏轮询
DEFAULT_POLL_INTERVAL = 5.0
DEFAULT_EXPIRES_IN = 7200.0
_HTTP_TIMEOUT = 15

# segno 在插件 deps/（ui/ 的上一级；与 gateway-wechat 同款打包方式）
_DEPS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "deps"))
if os.path.isdir(_DEPS) and _DEPS not in sys.path:
    sys.path.insert(0, _DEPS)


def render_qr_png(qr_text: str, scale: int = 12) -> bytes:
    """segno 渲染二维码 PNG（scale 12 ≈ 540px 源，420px 展示仍清晰可扫）。"""
    import segno

    qr = segno.make(qr_text, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=scale, border=2)
    return buf.getvalue()


def _post(path: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """JSON POST，errcode!=0 视为拒绝（对齐 device-auth.mjs assertRecord）。"""
    import httpx

    resp = httpx.post(
        f"{REGISTRATION_BASE_URL}{path}",
        json=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=httpx.Timeout(_HTTP_TIMEOUT, connect=10.0),
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    if not isinstance(data, dict):
        raise RuntimeError("钉钉返回了非对象响应")
    errcode = data.get("errcode")
    if errcode is not None and int(errcode) != 0:
        raise RuntimeError(f"钉钉拒绝（errcode={errcode}）: {str(data.get('errmsg'))[:120]}")
    return data


def fetch_qr() -> Tuple[str, bytes]:
    """发起设备注册，返回 (device_code, 二维码 PNG 字节)。失败抛异常。"""
    initialized = _post("/app/registration/init", {"source": REGISTRATION_SOURCE})
    nonce = str(initialized.get("nonce") or "").strip()
    if not nonce:
        raise RuntimeError("钉钉初始化未返回 nonce")

    begun = _post("/app/registration/begin", {"nonce": nonce})
    device_code = str(begun.get("device_code") or "").strip()
    verification_url = str(begun.get("verification_uri_complete") or "").strip()
    if not device_code or not verification_url:
        raise RuntimeError("钉钉注册未返回完整二维码信息")
    return device_code, render_qr_png(verification_url)


def poll_once(device_code: str) -> Dict[str, Any]:
    """查询一次注册状态，返回归一化 dict：
    {status: waiting/success/fail/expired, client_id, client_secret, fail_reason}
    """
    resp = _post("/app/registration/poll", {"device_code": device_code})
    raw = str(resp.get("status") or "").strip().upper()
    status = raw if raw in ("WAITING", "SUCCESS", "FAIL", "EXPIRED") else "WAITING"
    return {
        "status": status.lower(),
        "client_id": str(resp.get("client_id") or "").strip(),
        "client_secret": str(resp.get("client_secret") or "").strip(),
        "fail_reason": str(resp.get("fail_reason") or "").strip(),
    }


def save_credentials(client_id: str, client_secret: str) -> str:
    """写入配置并触发网关重建重连，返回给用户看的状态说明。"""
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    store = PluginConfigStore()
    store.set_values(PLUGIN_NAME, {"client_id": client_id, "client_secret": client_secret})
    try:
        if not bool(store.get(PLUGIN_NAME, "enabled")):
            logger.info("[dingtalk_login] 凭据已写入（网关未启用，开启开关后连接）")
            return "登录成功，凭据已保存。打开上方开关即可连接。"
        from app.gateway.manager import get_platform_manager

        mgr = get_platform_manager()
        if mgr is None:
            logger.info("[dingtalk_login] 凭据已写入（网关管理器未初始化）")
            return "登录成功，凭据已保存。网关启动后自动连接。"
        mgr.rebuild_plugin_platforms(PLUGIN_NAME, restart_if_running=True)
        logger.info("[dingtalk_login] 凭据已写入，网关已重建重连")
        return "登录成功，凭据已保存，网关已重连。"
    except Exception as e:  # noqa: BLE001 — 重连失败不影响凭据落盘
        logger.warning(f"[dingtalk_login] 自动重连未触发（可手动开关启用）: {e}")
        return "登录成功，凭据已保存。重连未触发，开关拨一次即可。"
