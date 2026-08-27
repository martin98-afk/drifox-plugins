# -*- coding: utf-8 -*-
"""
微信 iLink 扫码登录工具

流程（对应 iLink 官方接口，协议参考 openhanako wechat-login.ts，Apache-2.0）：
    1. get_qr:   GET /ilink/bot/get_bot_qrcode → 二维码内容 → segno 渲染 PNG → image_data 直接回显对话
    2. poll:     GET /ilink/bot/get_qrcode_status（35s 长轮询）→ confirmed → bot_token 写入配置
    3. status:   查看当前 token / 连接状态

token 失效（约 24h 或服务端踢下线）后重新扫码即可。
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.parse
from typing import Any, Dict

# ── 插件自包含依赖：segno（零依赖二维码库）vendor 到插件 deps/ ──
_deps = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "deps"))
if _deps not in sys.path:
    sys.path.insert(0, _deps)

from loguru import logger

from app.tools.result import ToolResult

LOGIN_BASE_URL = "https://ilinkai.weixin.qq.com"
BOT_TYPE = "3"
POLL_TIMEOUT = 45  # 服务端 hold 35s + 余量
GET_QR_TIMEOUT = 15


def _login_headers() -> Dict[str, str]:
    return {"iLink-App-ClientVersion": "1"}


def _http_get(url: str, timeout: int = POLL_TIMEOUT) -> Dict[str, Any]:
    """同步 GET（工具在 executor 线程跑，阻塞可接受）。

    长轮询接口服务端 hold 35s，读超时须大于它；connect 独立短超时。
    """
    import httpx

    resp = httpx.get(
        url,
        headers=_login_headers(),
        timeout=httpx.Timeout(timeout, connect=10.0),
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def _render_qr_png(qr_text: str, scale: int = 12) -> bytes:
    """segno 渲染二维码 PNG，返回字节（scale 12 ≈ 540px 源，420px 展示仍清晰可扫）"""
    import io

    import segno

    qr = segno.make(qr_text, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=scale, border=2)
    return buf.getvalue()


def _save_bot_token(token: str) -> None:
    """confirmed 后写入插件配置并触发网关重建重连（扫码后免重启）"""
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    PluginConfigStore().set_values(
        "gateway-wechat",
        {"bot_token": token},
    )
    # 重建 adapter（旧实例持有旧空 token 配置）并重启连接；
    # 未启用时不启动（用户开开关时自会触发）
    try:
        from app.plugins.managers.plugin_config_store import PluginConfigStore as _S

        enabled = bool(_S().get("gateway-wechat", "enabled"))
        if enabled:
            from app.gateway.manager import get_platform_manager

            mgr = get_platform_manager()
            if mgr is not None:
                mgr.rebuild_plugin_platforms("gateway-wechat", restart_if_running=True)
                logger.info("[wechat_login] token 已写入，网关已重建重连")
            else:
                logger.info("[wechat_login] token 已写入（网关管理器未初始化）")
        else:
            logger.info("[wechat_login] token 已写入（网关未启用，开启开关后连接）")
    except Exception as e:
        logger.warning(f"[wechat_login] 自动重连未触发（可手动开关启用）: {e}")


def _wechat_login_impl(tool_ctx, **kwargs) -> ToolResult:
    """impl: (tool_ctx, **kwargs) 唯一入参契约"""
    action = str(kwargs.get("action") or "status")

    try:
        if action == "get_qr":
            url = f"{LOGIN_BASE_URL}/ilink/bot/get_bot_qrcode?bot_type={BOT_TYPE}"
            data = _http_get(url, timeout=GET_QR_TIMEOUT)
            qr_content = data.get("qrcode_img_content") or data.get("qrcode")
            qrcode_id = data.get("qrcode")
            if not qr_content or not qrcode_id:
                return ToolResult(False, error=f"服务器未返回二维码: {json.dumps(data, ensure_ascii=False)[:200]}")

            png_bytes = _render_qr_png(str(qr_content))
            return ToolResult(
                True,
                content=(
                    "请用微信扫码登录（扫屏幕或截图识别均可）。\n\n"
                    f"扫完并手机确认后，调用 wechat_login(action=\"poll\", qrcode_id=\"{qrcode_id}\") 等待确认。\n"
                    "二维码约 2 分钟内有效，过期重新 get_qr。"
                ),
                image_data={"mime": "image/png", "data": base64.b64encode(png_bytes).decode()},
                data={"qrcode_id": qrcode_id, "status": "pending"},
            )

        if action == "poll":
            qrcode_id = str(kwargs.get("qrcode_id") or "")
            if not qrcode_id:
                return ToolResult(False, error="缺少 qrcode_id（先 action=get_qr）")

            url = f"{LOGIN_BASE_URL}/ilink/bot/get_qrcode_status?qrcode={urllib.parse.quote(qrcode_id)}"
            data = _http_get(url)

            status = str(data.get("status") or "waiting")
            if status in ("wait", "waiting"):
                return ToolResult(True, content="等待扫码中（本次长轮询约 35s 内无事件），请再调用一次 poll。", data={"status": "waiting"})
            if status == "scaned":
                return ToolResult(True, content="已扫码，等待用户在手机上点确认。再调用一次 poll。", data={"status": "scaned"})
            if status == "expired":
                return ToolResult(False, error="二维码已过期，请重新 get_qr。")
            if status == "confirmed":
                token = data.get("bot_token")
                if not token:
                    return ToolResult(False, error="登录成功但服务器未返回 bot_token")
                _save_bot_token(str(token))
                return ToolResult(
                    True,
                    content=(
                        "✅ 微信登录成功！bot_token 已写入 gateway-wechat 配置。\n"
                        f"bot_id: {data.get('ilink_bot_id', '')}\n"
                        "请在设置中启用「微信网关」开关，即可收发消息。"
                    ),
                    data={"status": "confirmed", "bot_id": str(data.get("ilink_bot_id") or "")},
                )
            return ToolResult(False, error=f"未知状态: {json.dumps(data, ensure_ascii=False)[:200]}")

        if action == "status":
            from app.plugins.managers.plugin_config_store import PluginConfigStore

            store = PluginConfigStore()
            token = store.get("gateway-wechat", "bot_token") or ""
            enabled = store.get("gateway-wechat", "enabled")
            has_token = bool(token)
            return ToolResult(
                True,
                content=(
                    f"微信网关状态：\n"
                    f"- enabled: {enabled}\n"
                    f"- bot_token: {'已配置（' + token[:8] + '…）' if has_token else '未配置'}\n"
                    + ("- 无 token：先 action=get_qr 扫码登录" if not has_token else "- 可用 action=get_qr 重新扫码换 token")
                ),
            )

        return ToolResult(False, error=f"未知 action: {action}（支持 get_qr / poll / status）")

    except Exception as e:
        logger.error("[wechat_login] error: %s", e, exc_info=True)
        return ToolResult(False, error=f"登录流程出错: {e}")


_WECHAT_LOGIN_SCHEMA = {
    "type": "function",
    "function": {
        "name": "wechat_login",
        "description": (
            "微信扫码登录工具（iLink 官方接口）。action=get_qr 生成登录二维码（直接在对话中显示）；"
            "action=poll 轮询扫码状态（confirmed 后自动写入 bot_token）；action=status 查看配置状态。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["get_qr", "poll", "status"],
                    "description": "get_qr=生成二维码；poll=轮询扫码状态；status=查看当前配置",
                },
                "qrcode_id": {
                    "type": "string",
                    "description": "poll 必填：get_qr 返回的 qrcode_id",
                },
            },
            "required": ["action"],
        },
    },
}


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "wechat_login",
        _WECHAT_LOGIN_SCHEMA,
        impl=_wechat_login_impl,
        danger="safe",
        cn_name="微信扫码登录",
        group="网关",
        description="生成微信 iLink 登录二维码 / 轮询扫码状态 / 查看配置",
        render_mode="inline",
    )
