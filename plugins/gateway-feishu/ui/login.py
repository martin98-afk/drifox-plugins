# -*- coding: utf-8 -*-
"""飞书应用注册扫码登录（官方设备授权端点，RFC 8628 变体）。

协议对齐 larksuite/node-sdk scene/registration/index.ts（MIT）与
dsh-im src/channels/feishu/*（MIT）：
    POST https://accounts.feishu.cn/oauth/v1/app/registration
        Content-Type: application/x-www-form-urlencoded
        action=begin & archetype=PersonalAgent & auth_method=client_secret
        & request_user_info=open_id
        → {device_code, verification_uri_complete, expires_in, interval}
    二维码 URL = verification_uri_complete + ?from=sdk&source=<x>&tp=sdk&addons=<enc>
        addons 编码：JSON({"scopes":{"tenant":[...]}}) → gzip → base64url 去 '='
    POST 同端点 action=poll & device_code=<dc>
        → 成功 {client_id, client_secret, user_info}
        → error: authorization_pending / slow_down / access_denied / expired_token
        RFC 8628：pending 类错误走 HTTP 400 + JSON body，必须读 body。
        user_info.tenant_brand == 'lark' 时 baseUrl 切 accounts.larksuite.com。

凭据产出 = app_id(cli_*) + app_secret，写插件配置（gateway.py 从 extra 读取）。
注意：扫码创建的应用需到飞书开放平台完成发布审批后才可正式使用。
"""

from __future__ import annotations

import base64
import gzip
import io
import json
import os
import sys
import urllib.parse
from typing import Any, Dict, Tuple

from loguru import logger

FEISHU_BASE_URL = "https://accounts.feishu.cn"
LARK_BASE_URL = "https://accounts.larksuite.com"
REGISTRATION_ENDPOINT = "/oauth/v1/app/registration"
PLUGIN_NAME = "gateway-feishu"
REGISTRATION_SOURCE = "drifox-gateway"

DEFAULT_POLL_INTERVAL = 5.0
DEFAULT_EXPIRES_IN = 600.0
_HTTP_TIMEOUT = 15

# 租户授权 scopes（对齐 dsh-im REQUIRED_TENANT_SCOPES，去掉其 slash 命令专用组）
REQUIRED_TENANT_SCOPES = [
    "im:message.p2p_msg:readonly",
    "im:message.group_at_msg:readonly",
    "im:message.group_at_msg.include_bot:readonly",
    "im:message.group_msg",
    "im:message:readonly",
    "im:message:send_as_bot",
    "im:message.reactions:write_only",
    "im:message:recall",
    "im:resource",
    "cardkit:card:write",
]

# segno 在插件 deps/（ui/ 的上一级；市场包按 manifest dependencies.pip 构建）
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


def encode_addons(scopes: Dict[str, Any]) -> str:
    """addons → JSON → gzip → base64url（+→-, /→_）去 '='（平台固定管线）。"""
    payload = json.dumps(scopes, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    b64 = base64.urlsafe_b64encode(gzip.compress(payload)).decode("ascii")
    return b64.rstrip("=")


def _registration_post(base_url: str, params: Dict[str, str]) -> Dict[str, Any]:
    """表单 POST；pending 类错误走 HTTP 400 + JSON body，照读不抛。"""
    import httpx

    resp = httpx.post(
        f"{base_url}{REGISTRATION_ENDPOINT}",
        content=urllib.parse.urlencode(params),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        timeout=httpx.Timeout(_HTTP_TIMEOUT, connect=10.0),
    )
    try:
        return resp.json()
    except Exception as e:  # noqa: BLE001 — 非 JSON 一律按网络错误处理
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}") from e


def fetch_qr() -> Tuple[str, str, bytes]:
    """发起应用注册，返回 (device_code, 二维码 URL, PNG 字节)。

    与 wechat/dingtalk 的二元组不同：飞书 poll 需要 baseUrl（lark 品牌切换），
    把当前 baseUrl 一并交给调用方。
    """
    begin_res = _registration_post(
        FEISHU_BASE_URL,
        {
            "action": "begin",
            "archetype": "PersonalAgent",
            "auth_method": "client_secret",
            "request_user_info": "open_id",
        },
    )
    device_code = str(begin_res.get("device_code") or "").strip()
    qr_url = str(begin_res.get("verification_uri_complete") or "").strip()
    if not device_code or not qr_url:
        raise RuntimeError(f"飞书未返回完整注册信息: {json.dumps(begin_res, ensure_ascii=False)[:160]}")

    # 拼官方 SDK 同款确认页参数：来源标识 + 一键带权限的 addons
    merged = urllib.parse.urlparse(qr_url)
    query = dict(urllib.parse.parse_qsl(merged.query, keep_blank_values=True))
    query.update(
        {
            "from": "sdk",
            "source": REGISTRATION_SOURCE,
            "tp": "sdk",
            "addons": encode_addons({"scopes": {"tenant": REQUIRED_TENANT_SCOPES}}),
        }
    )
    final_url = urllib.parse.ParseResult(
        scheme=merged.scheme,
        netloc=merged.netloc,
        path=merged.path,
        params=merged.params,
        query=urllib.parse.urlencode(query),
        fragment=merged.fragment,
    ).geturl()
    return device_code, final_url, render_qr_png(final_url)


def poll_once(device_code: str, base_url: str = FEISHU_BASE_URL) -> Dict[str, Any]:
    """查询一次注册状态，返回归一化 dict：
    {status: waiting/success/slow_down/access_denied/expired_token,
     app_id, app_secret, base_url(可能因 lark 品牌切换)}
    """
    resp = _registration_post(base_url, {"action": "poll", "device_code": device_code})
    client_id = str(resp.get("client_id") or "").strip()
    client_secret = str(resp.get("client_secret") or "").strip()
    if client_id and client_secret:
        return {"status": "success", "app_id": client_id, "app_secret": client_secret, "base_url": base_url}

    # lark 海外品牌切换（一次）：后续 poll 改走 accounts.larksuite.com
    user_info = resp.get("user_info")
    if isinstance(user_info, dict) and user_info.get("tenant_brand") == "lark" and base_url != LARK_BASE_URL:
        return {"status": "waiting", "app_id": "", "app_secret": "", "base_url": LARK_BASE_URL}

    error = str(resp.get("error") or "").strip()
    if error in ("authorization_pending", "", None):
        status = "waiting"
    elif error == "slow_down":
        status = "slow_down"
    elif error in ("access_denied", "expired_token"):
        status = error
    else:
        status = "access_denied"  # 未知错误按终止处理，附原因
    return {
        "status": status,
        "app_id": "",
        "app_secret": "",
        "base_url": base_url,
        "error_description": str(resp.get("error_description") or "").strip(),
    }


def save_credentials(app_id: str, app_secret: str) -> str:
    """写入配置并触发网关重建重连，返回给用户看的状态说明。"""
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    store = PluginConfigStore()
    store.set_values(PLUGIN_NAME, {"app_id": app_id, "app_secret": app_secret})
    try:
        if not bool(store.get(PLUGIN_NAME, "enabled")):
            logger.info("[feishu_login] 凭据已写入（网关未启用，开启开关后连接）")
            return "登录成功，凭据已保存。打开上方开关即可连接。"
        from app.gateway.manager import get_platform_manager

        mgr = get_platform_manager()
        if mgr is None:
            logger.info("[feishu_login] 凭据已写入（网关管理器未初始化）")
            return "登录成功，凭据已保存。网关启动后自动连接。"
        mgr.rebuild_plugin_platforms(PLUGIN_NAME, restart_if_running=True)
        logger.info("[feishu_login] 凭据已写入，网关已重建重连")
        return "登录成功，凭据已保存，网关已重连。"
    except Exception as e:  # noqa: BLE001 — 重连失败不影响凭据落盘
        logger.warning(f"[feishu_login] 自动重连未触发（可手动开关启用）: {e}")
        return "登录成功，凭据已保存。重连未触发，开关拨一次即可。"


def wait_gateway_connected(timeout: float = 30.0, cancel_check=None) -> bool:
    """等本插件网关平台真正连接成功（rebuild 触发的重连是异步的）。

    网关未启用 / 管理器未初始化 / 主开关未运行时无连接可等，直接 True
    （连接交给启动期兜底）；轮询超时或用户取消返回 False。
    """
    import time as _time

    try:
        from app.plugins.managers.plugin_config_store import PluginConfigStore

        if not bool(PluginConfigStore().get(PLUGIN_NAME, "enabled")):
            return True
        from app.gateway.manager import get_platform_manager

        mgr = get_platform_manager()
        if mgr is None or not mgr.get_status().get("running"):
            return True
        from app.plugins.registries.gateway_platform_registry import GatewayPlatformRegistry

        pids = GatewayPlatformRegistry.get_instance().get_platform_ids_by_source(
            f"plugin:{PLUGIN_NAME}"
        )
        if not pids:
            return True
        deadline = _time.monotonic() + timeout
        while _time.monotonic() < deadline:
            if cancel_check is not None and cancel_check():
                return False
            platforms = mgr.get_status().get("platforms") or {}
            if all(bool(platforms.get(p, {}).get("connected")) for p in pids):
                return True
            _time.sleep(1.0)
        return False
    except Exception as e:  # noqa: BLE001 — 状态不可知时不阻塞登录结果
        logger.debug(f"[{PLUGIN_NAME}] 网关连接状态不可查询: {e}")
        return True
