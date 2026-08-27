# -*- coding: utf-8 -*-
"""
微信 iLink 扫码登录工具

流程（对应 iLink 官方接口，协议参考 openhanako wechat-login.ts，Apache-2.0）：
    1. get_qr:   GET /ilink/bot/get_bot_qrcode → 二维码内容 → segno 渲染 PNG → 返回本地路径
    2. poll:     GET /ilink/bot/get_qrcode_status（35s 长轮询）→ confirmed → bot_token 写入配置
    3. status:   查看当前 token / 连接状态

token 失效（约 24h 或服务端踢下线）后重新扫码即可。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Dict

# ── 插件自包含依赖：segno（零依赖二维码库）vendor 到插件 deps/ ──
_deps = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "deps"))
if _deps not in sys.path:
    sys.path.insert(0, _deps)

from loguru import logger

from app.tools.result import ToolResult

LOGIN_BASE_URL = "https://ilinkai.weixin.qq.com"
BOT_TYPE = "3"
POLL_TIMEOUT = 40  # 服务端 hold 35s + 余量


def _login_headers() -> Dict[str, str]:
    return {"iLink-App-ClientVersion": "1"}


def _http_get(url: str, timeout: int = POLL_TIMEOUT) -> Dict[str, Any]:
    """同步 GET（工具在 executor 线程跑，阻塞可接受）"""
    import httpx

    resp = httpx.get(url, headers=_login_headers(), timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def _qr_png_path() -> Path:
    """二维码 PNG 输出路径（宿主数据目录）"""
    from app.gateway.base import get_cache_dir

    d = get_cache_dir("wechat")
    return d / "login_qr.png"


def _render_qr(qr_text: str) -> str:
    """segno 渲染 PNG，返回绝对路径"""
    import segno

    qr = segno.make(qr_text, error="m")
    path = _qr_png_path()
    qr.save(str(path), scale=8, border=2)
    return str(path)


def _save_bot_token(token: str) -> None:
    """confirmed 后写入插件配置"""
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    PluginConfigStore().set_values(
        "gateway-wechat",
        {"bot_token": token},
    )


def _wechat_login_impl(tool_ctx, **kwargs) -> ToolResult:
    """impl: (tool_ctx, **kwargs) 唯一入参契约"""
    action = str(kwargs.get("action") or "status")

    try:
        if action == "get_qr":
            url = f"{LOGIN_BASE_URL}/ilink/bot/get_bot_qrcode?bot_type={BOT_TYPE}"
            data = _http_get(url, timeout=15)
            qr_content = data.get("qrcode_img_content") or data.get("qrcode")
            qrcode_id = data.get("qrcode")
            if not qr_content or not qrcode_id:
                return ToolResult(False, error=f"服务器未返回二维码: {json.dumps(data, ensure_ascii=False)[:200]}")

            png_path = _render_qr(str(qr_content))
            return ToolResult(
                True,
                content=(
                    f"二维码已生成：{png_path}\n\n"
                    f"请用微信扫码（打开图片后扫一扫）。二维码内容前缀：{str(qr_content)[:50]}…\n"
                    f"qrcode_id: {qrcode_id}\n\n"
                    f"扫码后调用 wechat_login(action=\"poll\", qrcode_id=\"{qrcode_id}\") 等待确认。"
                ),
                data={"qrcode_id": qrcode_id, "qr_png": png_path},
            )

        if action == "poll":
            qrcode_id = str(kwargs.get("qrcode_id") or "")
            if not qrcode_id:
                return ToolResult(False, error="缺少 qrcode_id（先 action=get_qr）")

            url = f"{LOGIN_BASE_URL}/ilink/bot/get_qrcode_status?qrcode={urllib.parse.quote(qrcode_id)}"
            data = _http_get(url)

            status = str(data.get("status") or "waiting")
            if status in ("wait", "waiting"):
                return ToolResult(True, content="等待扫码中（长轮询一次约 35s），请再调用一次 poll。", data={"status": "waiting"})
            if status == "scaned":
                return ToolResult(True, content="已扫码，等待用户在手机上确认。再调用一次 poll。", data={"status": "scanned"})
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
                        "请在设置中启用「微信网关」开关，或让用户直接发消息测试。"
                    ),
                    data={
                        "status": "confirmed",
                        "bot_token": str(token),
                        "ilink_bot_id": data.get("ilink_bot_id"),
                        "ilink_user_id": data.get("ilink_user_id"),
                    },
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
            "微信扫码登录工具（iLink 官方接口）。action=get_qr 生成登录二维码 PNG 并返回路径；"
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
