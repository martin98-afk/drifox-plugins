# -*- coding: utf-8 -*-
"""OpenAI Codex 认证客户端 — Device Flow 登录 / 刷新（纯标准库）。

协议来源：openai/codex 官方源码 codex-rs/login/src/device_code_auth.rs +
oauth/client.rs（2026-10 校准），并经真实端点实测：

- 设备注册  POST https://auth.openai.com/api/accounts/deviceauth/usercode
            JSON {client_id} → {device_auth_id, user_code, interval}
            （注意：与旧社区资料不同，注册请求不带 scope/PKCE——PKCE verifier
            由服务端生成，轮询成功时随 authorization_code 一并下发）
- 授权页    https://auth.openai.com/codex/device（用户手输 user_code，15 分钟有效）
- 轮询授权  POST https://auth.openai.com/api/accounts/deviceauth/token
            JSON {device_auth_id, user_code}
            HTTP 403/404 = 未授权继续等；成功 → {authorization_code,
            code_challenge, code_verifier}
- 换取令牌  POST https://auth.openai.com/oauth/token
            form: grant_type=authorization_code + code + redirect_uri(=
            https://auth.openai.com/deviceauth/callback) + client_id +
            code_verifier（服务端下发值）
            官方 oauth/client.rs：authorization_code 走 form，refresh 走 JSON
- 刷新令牌  同端点 JSON {grant_type: "refresh_token", client_id, refresh_token}；
            refresh_token 可能轮换，以响应新值为准
- 账号标识  id_token（JWT）claims["https://api.openai.com/auth"]["chatgpt_account_id"]

CF 防护：auth.openai.com 所有请求必须带 originator: codex_cli_rs 头（缺省被
Cloudflare 530 拒绝，实测校准）。

聊天端点：https://chatgpt.com/backend-api/codex（OpenAI Responses API 形态，
POST {base}/responses），走 ChatGPT 订阅额度，需 Plus/Pro/Business 等订阅。

风险提示：非官方客户端协议实现，存在违反服务条款与封号风险，请自行评估。
"""
import base64
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from typing import Any, Dict, Optional

AUTH_ENDPOINT = "https://auth.openai.com"
DEVICE_CODE_PATH = "/api/accounts/deviceauth/usercode"
DEVICE_POLL_PATH = "/api/accounts/deviceauth/token"
TOKEN_PATH = "/oauth/token"
DEVICE_REDIRECT_URI = "https://auth.openai.com/deviceauth/callback"
VERIFICATION_URL = "https://auth.openai.com/codex/device"

# Codex CLI 的公开 OAuth client_id（社区实现通用值）
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"

AUTH_CLAIMS_NAMESPACE = "https://api.openai.com/auth"

# 过 Cloudflare 防护的伪装头（originator 缺失会被 530 拒绝，实测校准）
_REQUEST_HEADERS = {
    "originator": "codex_cli_rs",
    "User-Agent": "codex_cli_rs/0.62.0 (Windows 11; x86_64) DriFox",
    "Accept": "application/json",
}

DEFAULT_TIMEOUT = 30.0
LOGIN_TIMEOUT = 900.0  # 官方设备码 15 分钟有效
SLOW_DOWN_EXTRA = 5.0
REFRESH_SKEW_SEC = 5 * 60  # 剩 5 分钟视为临期


def _wrap_net_error(exc: Exception) -> RuntimeError:
    return RuntimeError(
        f"OpenAI 连接失败（{exc.__class__.__name__}）：请检查网络/代理是否能访问 auth.openai.com"
    )


def _read_body(exc: urllib.error.HTTPError) -> Dict[str, Any]:
    """读 HTTPError 响应体为 JSON（设备轮询的 pending 态走 4xx 传 JSON）。"""
    try:
        return json.loads(exc.read().decode("utf-8", errors="replace"))
    except Exception:  # noqa: BLE001 —— body 非法时按空 dict 处理
        return {}


def _post(
    url: str,
    *,
    form: Optional[Dict[str, str]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """POST 并解析 JSON（form / JSON 双形态；官方：authorization_code 走 form，refresh 走 JSON）。"""
    if form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
        headers = {"Content-Type": "application/x-www-form-urlencoded", **_REQUEST_HEADERS}
    else:
        data = json.dumps(json_body or {}).encode("utf-8")
        headers = {"Content-Type": "application/json", **_REQUEST_HEADERS}
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        payload = _read_body(exc)
        if payload:
            return payload
        return {"error": "http_error", "error_description": f"HTTP {exc.code}"}
    except (urllib.error.URLError, OSError) as exc:
        raise _wrap_net_error(exc) from exc


def start_device_flow() -> Dict[str, Any]:
    """发起 Device Flow：返回 {device_auth_id, user_code, interval, verification_url}。

    注册请求只带 client_id（官方 UserCodeReq 形态）；PKCE 由服务端生成。
    """
    payload = _post(
        f"{AUTH_ENDPOINT}{DEVICE_CODE_PATH}",
        json_body={"client_id": CLIENT_ID},
    )
    if not (payload.get("device_auth_id") and payload.get("user_code")):
        error = payload.get("error")
        raise RuntimeError(f"deviceauth/usercode 响应异常: {error or payload}")
    try:
        interval = int(str(payload.get("interval", "5")).strip())
    except ValueError:
        interval = 5
    return {
        "device_auth_id": payload["device_auth_id"],
        "user_code": payload["user_code"],
        "interval": max(interval, 2),
        "verification_url": VERIFICATION_URL,
    }


def poll_authorization_code(
    device_auth_id: str,
    user_code: str,
    interval: float,
    timeout_sec: float = LOGIN_TIMEOUT,
) -> Dict[str, Any]:
    """轮询设备授权结果：成功返回 {authorization_code, code_verifier, code_challenge}。

    官方逻辑：HTTP 403/404 = 未授权继续等（15 分钟超时）；其余错误直接抛出。
    """
    deadline = time.time() + timeout_sec
    wait = interval
    while time.time() < deadline:
        payload = _post(
            f"{AUTH_ENDPOINT}{DEVICE_POLL_PATH}",
            json_body={"device_auth_id": device_auth_id, "user_code": user_code},
        )
        code = payload.get("authorization_code", "")
        if code and payload.get("code_verifier"):
            return {
                "authorization_code": code,
                "code_verifier": payload["code_verifier"],
                "code_challenge": payload.get("code_challenge", ""),
            }
        # pending 判定：403 {"error":{"code":"deviceauth_authorization_pending"}}
        # （实测形态）或平铺 error 字符串（兼容形态），均按「继续等」处理；
        # 其余错误（参数错/端点变更等）立即抛出，避免空等满超时
        error = payload.get("error")
        error_code = error.get("code", "") if isinstance(error, dict) else error
        pending = error_code in (
            "deviceauth_authorization_pending",
            "authorization_pending",
            "slow_down",
        )
        if not pending:
            desc = error.get("message") if isinstance(error, dict) else (error or payload)
            raise RuntimeError(f"OpenAI 设备授权轮询失败: {desc}")
        time.sleep(wait)
    raise TimeoutError("等待 OpenAI 授权超时（未在期限内完成浏览器授权，设备码 15 分钟有效）")


def decode_jwt_claims(token: str) -> Dict[str, Any]:
    """解 JWT payload（不验签，仅本地取 chatgpt_account_id 等展示性 claim）。"""
    if not token or token.count(".") < 2:
        return {}
    try:
        _, payload, _ = token.split(".", 2)
        padded = payload + "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _extract_account_id(token_payload: Dict[str, Any]) -> str:
    """从 token 响应的 id_token 提取 ChatGPT 账号 ID（取不到返回空串，头自动省略）。"""
    claims = decode_jwt_claims(str(token_payload.get("id_token", "") or ""))
    auth = claims.get(AUTH_CLAIMS_NAMESPACE)
    if isinstance(auth, dict):
        return str(auth.get("chatgpt_account_id", "") or "")
    return ""


def exchange_code(authorization_code: str, code_verifier: str) -> Dict[str, Any]:
    """authorization_code 换 token 组（form 编码，官方 authorization-code 走 form）。

    返回 {access_token, refresh_token, expires_in, account_id}。
    """
    payload = _post(
        f"{AUTH_ENDPOINT}{TOKEN_PATH}",
        form={
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": DEVICE_REDIRECT_URI,
            "client_id": CLIENT_ID,
            "code_verifier": code_verifier,
        },
    )
    if not payload.get("access_token"):
        raise RuntimeError(f"换取 token 失败: {payload.get('error_description') or payload}")
    return {
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token", ""),
        "expires_in": int(payload.get("expires_in") or 0),
        "account_id": _extract_account_id(payload),
    }


def refresh_tokens(refresh_token: str) -> Dict[str, Any]:
    """刷新 token 组（JSON 编码，官方 ChatGPT refresh 走 JSON）。

    返回结构同 exchange_code；refresh_token 以响应新值为准（轮换时旧值兜底）。
    """
    payload = _post(
        f"{AUTH_ENDPOINT}{TOKEN_PATH}",
        json_body={
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "refresh_token": refresh_token,
        },
    )
    if not payload.get("access_token"):
        raise RuntimeError(f"刷新 token 失败: {payload.get('error_description') or payload}")
    return {
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token", "") or refresh_token,
        "expires_in": int(payload.get("expires_in") or 0),
        "account_id": _extract_account_id(payload),
    }


def login(
    timeout_sec: float = LOGIN_TIMEOUT,
    open_browser: bool = True,
) -> Dict[str, Any]:
    """完整 Device Flow 登录（对齐官方 run_device_code_login）。

    打开授权页 + 复制 user_code 到剪贴板 + 轮询 + 用服务端 verifier 换 token。
    返回 {"refresh_token", "account_id", "user_code", "verification_url"}；
    超时抛 TimeoutError。refresh_token 为长效凭证（存配置 API_KEY 字段），
    短效 access_token 由 provider 层按需换取。
    """
    flow = start_device_flow()
    if open_browser:
        webbrowser.open(flow["verification_url"])
    _copy_to_clipboard(flow["user_code"])
    polled = poll_authorization_code(
        flow["device_auth_id"], flow["user_code"], flow["interval"], timeout_sec=timeout_sec
    )
    tokens = exchange_code(polled["authorization_code"], polled["code_verifier"])
    if not tokens["refresh_token"]:
        raise RuntimeError("OpenAI 未返回 refresh_token，请重试登录")
    # 预热账号 ID：登录后立即解 id_token，缓存首写即含 account_id
    return {
        "refresh_token": tokens["refresh_token"],
        "account_id": tokens["account_id"],
        "user_code": flow["user_code"],
        "verification_url": flow["verification_url"],
    }


def _copy_to_clipboard(text: str) -> bool:
    """跨平台剪贴板复制（纯外部命令，逐个尝试；全部失败返回 False 不阻塞登录）。

    Windows clip.exe 需带 BOM 的 UTF-16（utf-16-le 无 BOM 会静默失败）。"""
    import subprocess

    commands = [
        (["clip"], text.encode("utf-16")),  # Windows clip.exe（UTF-16 带 BOM）
        (["pbcopy"], text.encode("utf-8")),  # macOS
        (["xclip", "-selection", "clipboard"], text.encode("utf-8")),  # X11
        (["wl-copy"], text.encode("utf-8")),  # Wayland
    ]
    for cmd, data in commands:
        try:
            subprocess.run(cmd, input=data, check=True, timeout=5)
            return True
        except Exception:
            continue
    return False
