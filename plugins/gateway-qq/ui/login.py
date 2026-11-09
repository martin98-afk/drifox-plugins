# -*- coding: utf-8 -*-
"""QQ 机器人绑定扫码登录（官方 q.qq.com 绑定任务接口，纯 HTTP）。

协议对齐 @tencent-connect/qqbot-connector 1.2.0 dist/esm/qqbot-session.js（MIT）：
    本地生成 32 字节随机 key（base64，用于回传 secret 的端到端解密）
    POST https://q.qq.com/lite/create_bind_task   {"key": <key>}  → {retcode, data:{task_id}}
    二维码内容 = https://q.qq.com/qqbot/openclaw/connect.html
                 ?task_id=<id>&source=<source>&_wv=2   （手机 QQ 扫码完成机器人绑定）
    POST https://q.qq.com/lite/poll_bind_result   {"task_id"}  (约 2s 间隔)
        → {retcode, data:{status:1 PENDING/2 COMPLETED/3 EXPIRED,
                          bot_appid, bot_encrypt_secret, user_openid}}
    解密：bot_encrypt_secret = base64(nonce(12B) + ciphertext + tag(16B))，
          AES-256-GCM，密钥即本地 key；明文为 AppSecret。

凭据产出 = appid + app_secret，写插件配置（gateway.py 从 bot_id/secret 读取，
配置键为 appid / app_secret）。
"""

from __future__ import annotations

import base64
import io
import secrets
from typing import Any, Dict, Tuple

from loguru import logger

QQ_BOT_HOST = "q.qq.com"
PLUGIN_NAME = "gateway-qq"
REGISTRATION_SOURCE = "drifox-gateway"

POLL_INTERVAL = 2.0  # 对齐 connector 的 2000ms
_HTTP_TIMEOUT = 15

# segno 在插件 deps/（ui/ 的上一级；市场包按 manifest dependencies.pip 构建）
import os
import sys

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
    import httpx

    resp = httpx.post(
        f"https://{QQ_BOT_HOST}{path}",
        json=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=httpx.Timeout(_HTTP_TIMEOUT, connect=10.0),
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    if not isinstance(data, dict):
        raise RuntimeError("QQ 开放平台返回了非对象响应")
    if data.get("retcode") != 0:
        raise RuntimeError(f"QQ 开放平台拒绝: {str(data.get('msg') or data.get('retcode'))[:120]}")
    return data


def _decrypt_secret(encrypted: str, key_b64: str) -> str:
    """AES-256-GCM 解密回传的 AppSecret：base64(nonce12 + ciphertext + tag16)。"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = base64.b64decode(key_b64)
    raw = base64.b64decode(encrypted)
    if len(raw) < 12 + 16:
        raise RuntimeError("QQ 回传的加密数据长度异常")
    nonce, payload = raw[:12], raw[12:]  # cryptography 要求 payload 末尾自带 16B tag
    return AESGCM(key).decrypt(nonce, payload, None).decode("utf-8")


def fetch_qr() -> Tuple[str, str, bytes]:
    """创建绑定任务，返回 (task_id, bind_key, 二维码 PNG 字节)。

    bind_key 仅存于本次登录会话内存，用于解密 poll 回传的 AppSecret，不落盘。
    """
    key = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    created = _post("/lite/create_bind_task", {"key": key})
    task_id = str((created.get("data") or {}).get("task_id") or "").strip()
    if not task_id:
        raise RuntimeError("QQ 创建绑定任务未返回 task_id")
    connect_url = (
        f"https://{QQ_BOT_HOST}/qqbot/openclaw/connect.html"
        f"?task_id={task_id}&source={REGISTRATION_SOURCE}&_wv=2"
    )
    return task_id, key, render_qr_png(connect_url)


def poll_once(task_id: str, key_b64: str) -> Dict[str, Any]:
    """查询一次绑定状态，返回归一化 dict：
    {status: waiting/success/expired, appid, app_secret}
    """
    resp = _post("/lite/poll_bind_result", {"task_id": task_id})
    payload = resp.get("data") or {}
    try:
        status = {1: "waiting", 2: "success", 3: "expired"}.get(
            int(payload.get("status")), "waiting"
        )
    except (TypeError, ValueError):
        status = "waiting"
    if status != "success":
        return {"status": status, "appid": "", "app_secret": ""}
    appid = str(payload.get("bot_appid") or "").strip()
    encrypted = str(payload.get("bot_encrypt_secret") or "").strip()
    if not appid or not encrypted:
        raise RuntimeError("QQ 绑定完成但回传数据不完整")
    return {
        "status": "success",
        "appid": appid,
        "app_secret": _decrypt_secret(encrypted, key_b64),
    }


def save_credentials(appid: str, app_secret: str) -> str:
    """写入配置并触发网关重建重连，返回给用户看的状态说明。"""
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    store = PluginConfigStore()
    store.set_values(PLUGIN_NAME, {"appid": appid, "app_secret": app_secret})
    try:
        if not bool(store.get(PLUGIN_NAME, "enabled")):
            logger.info("[qq_login] 凭据已写入（网关未启用，开启开关后连接）")
            return "登录成功，凭据已保存。打开上方开关即可连接。"
        from app.gateway.manager import get_platform_manager

        mgr = get_platform_manager()
        if mgr is None:
            logger.info("[qq_login] 凭据已写入（网关管理器未初始化）")
            return "登录成功，凭据已保存。网关启动后自动连接。"
        mgr.rebuild_plugin_platforms(PLUGIN_NAME, restart_if_running=True)
        logger.info("[qq_login] 凭据已写入，网关已重建重连")
        return "登录成功，凭据已保存，网关已重连。"
    except Exception as e:  # noqa: BLE001 — 重连失败不影响凭据落盘
        logger.warning(f"[qq_login] 自动重连未触发（可手动开关启用）: {e}")
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
