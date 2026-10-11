# -*- coding: utf-8 -*-
"""xAI (Grok) 认证客户端 — OAuth 2.0 Device Flow 登录 / 刷新（纯标准库）。

协议来源：xAI 官方 OIDC 端点（auth.x.ai/.well-known/openid-configuration），
客户端参数与 Grok CLI / OpenCode / pi-xai-oauth 等公开实现一致（2026-10 校准）：

- 设备端点   https://auth.x.ai/oauth2/device/code
- 令牌端点   https://auth.x.ai/oauth2/token
- client_id  b1a00492-073a-47ea-816f-4c329264a828（公开 OAuth client 标识）
- scope      openid profile email offline_access grok-cli:access api:access
             conversations:read conversations:write（与 Grok CLI 完全一致，
             保障订阅权益判定）

登录流程（Device Flow，与 codex-oauth 插件同形态）：
    本端请求设备码（得到 user_code + verification_uri）→ 浏览器打开授权页 →
    用户登录 SuperGrok / X Premium+ 账号，页面展示机器码输入/确认 → 本端按
    interval 轮询令牌端点（authorization_pending 继续 / slow_down 退避）→
    授权通过后换得 token 组。

说明：xAI 对本 client 的浏览器授权页即「输入此代码以完成登录」形态（机器码
确认页），PKCE + loopback 回调在该页不成立，故走 Device Flow。

刷新：同令牌端点 grant_type=refresh_token（access/refresh 均可能轮换，以响应
新值为准）。令牌端点请求：标准 OAuth2 form 表单。

风险提示：非官方客户端协议实现，存在违反服务条款与封号风险，请自行评估。
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from typing import Any, Dict

DEVICE_ENDPOINT = "https://auth.x.ai/oauth2/device/code"
TOKEN_ENDPOINT = "https://auth.x.ai/oauth2/token"

# Grok CLI 的公开 OAuth client_id（社区实现通用值）
CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
SCOPE = (
    "openid profile email offline_access grok-cli:access "
    "api:access conversations:read conversations:write"
)

DEFAULT_TIMEOUT = 30.0
LOGIN_TIMEOUT = 900.0  # 15 分钟（对齐 Device Flow 惯例上限）
POLL_INTERVAL = 5.0  # 官方响应 interval 缺省时的兜底
SLOW_DOWN_DELTA = 5.0  # slow_down 时轮询间隔增量（RFC 8628）


def _post_form(url: str, body: Dict[str, Any], timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """标准 OAuth2 form POST。"""
    req = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "grok-cli/1.0 (DriFox)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # OAuth2 错误响应（400 + JSON body：authorization_pending / slow_down 等）走这里
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        if payload:
            return payload
        raise RuntimeError(f"xAI 端点拒绝: HTTP {exc.code}: {raw[:200]}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(
            f"xAI 连接失败（{exc.__class__.__name__}）：请检查网络/代理是否能访问 auth.x.ai"
        ) from exc


def request_device_code() -> Dict[str, Any]:
    """请求设备码。

    返回 {"device_code", "user_code", "verification_uri", "expires_in", "interval"}；
    verification_uri_complete（含预填 code 的完整链接）存在时一并透传。
    """
    payload = _post_form(DEVICE_ENDPOINT, {"client_id": CLIENT_ID, "scope": SCOPE})
    if not payload.get("device_code") or not payload.get("user_code"):
        desc = payload.get("error_description") or payload.get("error") or payload
        raise RuntimeError(f"xAI 设备码请求失败: {desc}")
    return {
        "device_code": payload["device_code"],
        "user_code": payload["user_code"],
        "verification_uri": payload.get("verification_uri") or "https://auth.x.ai/activate",
        "verification_uri_complete": payload.get("verification_uri_complete", ""),
        "expires_in": int(payload.get("expires_in") or 600),
        "interval": float(payload.get("interval") or POLL_INTERVAL),
    }


def poll_token(device_code: str, interval: float, timeout_sec: float) -> Dict[str, Any]:
    """按 interval 轮询令牌端点直至授权完成/超时。

    RFC 8628 状态机：authorization_pending 继续；slow_down 退避；其余错误抛出。
    """
    deadline = time.time() + timeout_sec
    cur_interval = max(interval, POLL_INTERVAL)
    while time.time() < deadline:
        time.sleep(cur_interval)
        payload = _post_form(
            TOKEN_ENDPOINT,
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": CLIENT_ID,
            },
        )
        if payload.get("access_token"):
            return {
                "access_token": payload["access_token"],
                "refresh_token": payload.get("refresh_token", ""),
                "expires_in": int(payload.get("expires_in") or 0),
            }
        err = payload.get("error", "")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            cur_interval += SLOW_DOWN_DELTA
            continue
        if err == "expired_token":
            raise RuntimeError("设备码已过期：请重新点击「登录」获取新机器码")
        if err == "access_denied":
            raise RuntimeError("授权被拒绝：请在浏览器页面点「允许/Authorize」")
        desc = payload.get("error_description") or err or payload
        raise RuntimeError(f"xAI 授权失败: {desc}")
    raise TimeoutError(
        f"等待授权超时（{int(timeout_sec / 60)} 分钟）：请重新点击「登录」并在页面完成机器码确认"
    )


def refresh_tokens(refresh_token: str) -> Dict[str, Any]:
    """刷新 token 组；refresh_token 以响应新值为准（轮换时旧值作兜底）。"""
    payload = _post_form(
        TOKEN_ENDPOINT,
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLIENT_ID,
        },
    )
    if not payload.get("access_token"):
        raise RuntimeError(f"刷新 token 失败: {payload}")
    return {
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token", "") or refresh_token,
        "expires_in": int(payload.get("expires_in") or 0),
    }


def login(
    timeout_sec: float = LOGIN_TIMEOUT,
    open_browser: bool = True,
) -> Dict[str, Any]:
    """完整登录（Device Flow 变体，codex-oauth 同形态）。

    请求设备码 → 浏览器打开 xAI 授权页 → 用户登录 SuperGrok / X Premium+ 并
    确认机器码 → 本端轮询令牌端点自动换取 token。

    返回 {"refresh_token", "expires_in"}；超时抛 TimeoutError。
    refresh_token 为长效凭证（存配置 API_KEY 字段），短效 access_token 由
    provider 层按需换取。
    """
    dev = request_device_code()
    url = dev.get("verification_uri_complete") or dev["verification_uri"]
    if open_browser:
        webbrowser.open(url)
    tokens = poll_token(dev["device_code"], dev["interval"], timeout_sec)
    if not tokens["refresh_token"]:
        raise RuntimeError("xAI 未返回 refresh_token（scope 缺失 offline_access？），请重试登录")
    return {"refresh_token": tokens["refresh_token"], "expires_in": tokens["expires_in"]}
