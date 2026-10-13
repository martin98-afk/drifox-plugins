# -*- coding: utf-8 -*-
"""CodeBuddy 国际版认证客户端 — 登录 / 刷新 / JWT 解析（纯标准库，可独立 CLI）。

协议来源：国际版网关 www.codebuddy.ai，与国内版 copilot.tencent.com 同构。
参照 opencode-codebuddy-oauth（minglo）/ pi-codebuddy-oauth（SoulChildTc，
MIT，2026-09/10 实测）与国内版 buddy_auth.py（2026-09 真机校准）。

端点一览：
- 登录  POST /v2/plugin/auth/state?platform=VSCode&ioa=1（X-No-* 匿名头）→
        浏览器授权 → 轮询 GET /v2/plugin/auth/token?state=...（token 一次性，
        code=0 只闪现一次，字段驼峰 accessToken/refreshToken）
- 刷新  POST /v2/plugin/auth/token/refresh —— refresh_token 同时放
        Authorization: Bearer 与 X-Refresh-Token 双头（服务端校验头未真机
        确认，对齐上游「双头保留，盲删 401」策略）

响应统一包裹 {code, message, data}，业务码以响应体为准。

风险提示：非官方客户端协议实现，存在违反服务条款与封号风险，自行评估。
"""

import base64
import json
import time
import webbrowser
from typing import Any, Dict, Optional

ENDPOINT = "https://www.codebuddy.ai"
DOMAIN = "www.codebuddy.ai"
PRODUCT = "SaaS"
PRODUCT_CODE = "codebuddy"
AGENT_INTENT = "craft"
PLATFORM = "VSCode"
IDE_NAME = "VSCode"
IDE_TYPE = "VSCode"
IDE_VERSION = "1.119.0"
APP_VERSION = "4.9.29177644"
ENV_ID = "production"
USER_AGENT = f"{IDE_NAME}/{IDE_VERSION} CodeBuddy/{APP_VERSION}"

DEFAULT_TIMEOUT = 30.0
LOGIN_TIMEOUT = 300.0
LOGIN_POLL_INTERVAL = 1.0

CODE_OK = 0
CODE_TOKEN_NOT_READY = 11217
CODE_ACCOUNT_NOT_READY = 12151

AUTH_STATE_PATH = "/v2/plugin/auth/state"
AUTH_TOKEN_PATH = "/v2/plugin/auth/token"
LOGIN_ACCOUNT_PATH = "/v2/plugin/login/account"
TOKEN_REFRESH_PATH = "/v2/plugin/auth/token/refresh"
USER_RESOURCE_PATH = "/v2/billing/meter/get-user-resource"

# 匿名请求头：登录链（auth/state、auth/token）显式声明无凭据上下文
_ANON_HEADERS = {
    "X-No-Authorization": "true",
    "X-No-User-Id": "true",
    "X-No-Enterprise-Id": "true",
    "X-No-Department-Info": "true",
}


def build_headers(access_token: str = "", refresh_token: str = "") -> Dict[str, str]:
    """构造 CodeBuddy 国际版网关请求头（伪装身份九件套 + 可选鉴权）。"""
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-Agent-Intent": AGENT_INTENT,
        "X-IDE-Type": IDE_TYPE,
        "X-IDE-Name": IDE_NAME,
        "X-IDE-Version": IDE_VERSION,
        "X-Product-Version": APP_VERSION,
        "X-Env-ID": ENV_ID,
        "X-Domain": DOMAIN,
        "X-Product": PRODUCT,
        "X-Product-Code": PRODUCT_CODE,
        "User-Agent": USER_AGENT,
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    if refresh_token:
        headers["X-Refresh-Token"] = refresh_token
    return headers


def build_anonymous_headers() -> Dict[str, str]:
    """登录链匿名头：伪装身份 + X-No-*（声明无凭据上下文）。"""
    headers = build_headers()
    headers.update(_ANON_HEADERS)
    headers.pop("Authorization", None)
    return headers


def parse_jwt_claims(access_token: str) -> Dict[str, Any]:
    """解 JWT payload 段（不验签，仅供租户身份头提取），失败返回空表。"""
    try:
        part = access_token.split(".")[1]
        part += "=" * (-len(part) % 4)
        payload = json.loads(base64.urlsafe_b64decode(part.encode()).decode("utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _identity_from_claims(claims: Dict[str, Any]) -> Dict[str, str]:
    """从 JWT claims 提租户三元组；字段名多候选兼容（未经真机全量校准）。"""
    ident: Dict[str, str] = {}
    for key, candidates in (
        ("X-Tenant-Id", ("tenant_id", "tenantId", "tid")),
        ("X-Enterprise-Id", ("enterprise_id", "enterpriseId", "eid")),
        ("X-User-Id", ("user_id", "userId", "uid", "sub")),
    ):
        for cand in candidates:
            val = claims.get(cand)
            if val:
                ident[key] = str(val)
                break
    return ident


def identity_headers(access_token: str) -> Dict[str, str]:
    """按 access_token 提取租户身份头（取不到返回空表，调用方省略注入）。"""
    return _identity_from_claims(parse_jwt_claims(access_token))


def _request(
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    access_token: str = "",
    refresh_token: str = "",
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """发请求并解析 JSON；HTTP 4xx/5xx 也读 body（错误码以业务码为准）。"""
    import urllib.error  # 延迟导入：对齐插件 AST 审计约束
    import urllib.request

    headers = build_headers(access_token, refresh_token)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(f"{ENDPOINT}{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"code": -1, "message": f"HTTP {exc.code}: {raw[:200]}"}


def _payload_data(payload: Dict[str, Any]) -> Dict[str, Any]:
    """取 {code, message, data} 包裹的 data 段；兼容顶层平铺。"""
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def login(
    timeout_sec: float = LOGIN_TIMEOUT,
    poll_interval: float = LOGIN_POLL_INTERVAL,
    open_browser: bool = True,
) -> Dict[str, Any]:
    """轮询式登录：弹浏览器授权后本地轮询换取凭据（不起本地端口）。

    返回 {"access_token", "refresh_token", "expires_in", "account"}；
    超时抛 TimeoutError，state 异常抛 RuntimeError。
    """
    import urllib.request

    body = json.dumps({}).encode("utf-8")
    req = urllib.request.Request(
        f"{ENDPOINT}{AUTH_STATE_PATH}?platform={PLATFORM}&ioa=1",
        data=body,
        method="POST",
        headers=build_anonymous_headers(),
    )
    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
        state_payload = json.loads(resp.read().decode("utf-8"))
    state_data = _payload_data(state_payload)
    state = state_data.get("state", "")
    auth_url = state_data.get("authUrl", "")
    if not state or not auth_url:
        raise RuntimeError(f"auth/state 响应异常: {state_payload}")
    if open_browser:
        webbrowser.open(auth_url)

    deadline = time.monotonic() + timeout_sec
    access_token = refresh_token = ""
    token: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        payload = _request("GET", f"{AUTH_TOKEN_PATH}?state={state}")
        if payload.get("code") == CODE_TOKEN_NOT_READY:
            time.sleep(poll_interval)
            continue
        token = _payload_data(payload)
        # 字段驼峰（国内版真机实测同款）；token 一次性：code=0 只闪现一次
        access_token = token.get("accessToken") or token.get("access_token", "")
        refresh_token = token.get("refreshToken") or token.get("refresh_token", "")
        if access_token:
            break
        time.sleep(poll_interval)
    if not access_token:
        raise TimeoutError("登录超时：未在限时内取到 token")

    # account 未就绪不阻塞登录（12151 容错）；失败只影响展示信息
    account: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        payload = _request("GET", f"{LOGIN_ACCOUNT_PATH}?state={state}", access_token=access_token)
        if payload.get("code") == CODE_ACCOUNT_NOT_READY:
            time.sleep(poll_interval)
            continue
        account = _payload_data(payload)
        break

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": token.get("expiresIn") or token.get("expires_in"),
        "account": account,
    }


def refresh(refresh_token: str) -> Dict[str, Any]:
    """用 refresh_token 静默换新凭据；服务端不回新 refresh_token 时沿用旧值。

    双头保留：Authorization: Bearer + X-Refresh-Token（服务端校验头未真机
    确认，盲删任意一侧都可能 401）。
    """
    payload = _request(
        "POST",
        TOKEN_REFRESH_PATH,
        body={},
        access_token=refresh_token,
        refresh_token=refresh_token,
    )
    if payload.get("code", CODE_OK) != CODE_OK:
        raise RuntimeError(f"刷新失败: {payload}")
    data = _payload_data(payload)
    return {
        "access_token": data.get("accessToken") or data.get("access_token", ""),
        "refresh_token": data.get("refreshToken") or data.get("refresh_token", "") or refresh_token,
    }


def fetch_config(access_token: str, timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """拉取 /v3/config（模型目录 + craft 智能体清单），返回原始 data 段。"""
    import urllib.request

    req = urllib.request.Request(f"{ENDPOINT}/v3/config", headers=build_headers(access_token))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("code", CODE_OK) != CODE_OK:
        raise RuntimeError(f"/v3/config 响应异常: {payload}")
    return _payload_data(payload)


def user_resources(access_token: str) -> list:
    """查询积分/套餐资源明细（2026-10-13 国际版真机验证：与国内版同构）。

    响应路径 data.Response.Data.Accounts[]，每条含 PackageCode / PackageName /
    CycleCapacitySizePrecise（总量）/ CycleCapacityRemainPrecise（剩余）/
    DeductionEndTime（到期）；签到 bonus 包与套餐包同列。ProductCode 国际版
    仍为 p_tcaca，实测传不传均 200 → 不传（未来变更不受影响）。
    发送积分 = 剩余。
    """
    import datetime

    now = datetime.datetime.now()
    body = {
        "PageNumber": 1,
        "PageSize": 100,
        "Status": [0, 3],  # AccountStatus: valid=0 / usedUp=3
        "PackageStartTimeRangeBegin": "2024-12-01 00:00:00",
        "PackageStartTimeRangeEnd": now.strftime("%Y-%m-%d %H:%M:%S"),
    }
    payload = _request("POST", USER_RESOURCE_PATH, body=body, access_token=access_token)
    if payload.get("code", CODE_OK) != CODE_OK:
        raise RuntimeError(f"get-user-resource 响应异常: {payload}")
    root = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    return (((root.get("Response") or {}).get("Data") or {}).get("Accounts")) or []


def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="CodeBuddy 国际版认证客户端")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login", help="弹浏览器授权，打印凭据 JSON")
    p_refresh = sub.add_parser("refresh", help="用 refresh_token 换新 access_token")
    p_refresh.add_argument("refresh_token")
    p_config = sub.add_parser("models", help="拉取 craft 智能体模型目录")
    p_config.add_argument("access_token")
    args = parser.parse_args()

    if args.cmd == "login":
        print(json.dumps(login(), ensure_ascii=False, indent=2))
    elif args.cmd == "refresh":
        print(json.dumps(refresh(args.refresh_token), ensure_ascii=False, indent=2))
    elif args.cmd == "models":
        print(json.dumps(fetch_config(args.access_token), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
