# -*- coding: utf-8 -*-
"""Anthropic (Claude) 认证客户端 — Claude Code OAuth 登录 / 刷新（纯标准库）。

协议来源：Claude Code CLI 公开的 OAuth 客户端参数，与 cedws/ANTHROPIC_AUTH.md、
opencode 等多个社区实现一致（2026-10 校准）：

- 授权端点   https://claude.ai/oauth/authorize
- 令牌端点   https://console.anthropic.com/v1/oauth/token
- 回调地址   https://console.anthropic.com/oauth/code/callback（Anthropic 托管页，
             授权完成后页面展示 code，无本地回传通道）
- client_id  9d1c250a-e61b-44d9-88ed-5944d1962f5e（Claude Code 公开值）
- PKCE       S256；Claude Code 风格 state 复用 code_verifier
- scope      org:create_api_key user:profile user:inference

登录流程（托管回调变体）：
    浏览器授权 → 回调页显示「code#state」→ 用户复制（Ctrl+C）→ 本端轮询
    剪贴板检测到含本会话 state 的串（天然防误触，state 每次随机）→ 取 # 前
    code 换取 token 组。

令牌端点请求头：Content-Type: application/json + User-Agent: anthropic（社区实现
必备，缺 User-Agent 会被拒）。

刷新：同端点 grant_type=refresh_token（access/refresh 均可能轮换，以响应新值为准）。

API 调用（OAuth 凭证与 API Key 路径不同）：
    Authorization: Bearer sk-ant-oat01-...
    anthropic-beta: oauth-2025-04-20（OAuth 凭证必需）

风险提示：非官方客户端协议实现，存在违反服务条款与封号风险，请自行评估。
"""
import base64
import hashlib
import json
import re
import secrets
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from typing import Any, Dict, Optional

AUTHORIZE_ENDPOINT = "https://claude.ai/oauth/authorize"
TOKEN_ENDPOINT = "https://console.anthropic.com/v1/oauth/token"
REDIRECT_URI = "https://console.anthropic.com/oauth/code/callback"

# Claude Code 的公开 OAuth client_id（社区实现通用值）
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
SCOPE = "org:create_api_key user:profile user:inference"

DEFAULT_TIMEOUT = 30.0
LOGIN_TIMEOUT = 300.0
LOGIN_POLL_INTERVAL = 2.0

# 回调页 code 形如「xxxxxx#state」，两段均为 URL 安全 base64 字符
_CODE_STATE_PATTERN = re.compile(r"^([A-Za-z0-9._~-]+)#([A-Za-z0-9._~-]+)$")


def generate_pkce() -> tuple:
    """生成 (code_verifier, code_challenge, state)：Claude Code 风格 state=verifier。"""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge, verifier


def build_authorize_url(code_challenge: str, state: str) -> str:
    """构造授权页 URL（code=true：回调页展示 code 供复制）。"""
    params = {
        "code": "true",
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    return f"{AUTHORIZE_ENDPOINT}?{urllib.parse.urlencode(params)}"


def _post_json(url: str, body: Dict[str, Any], timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """JSON POST（令牌端点要求 JSON body + User-Agent: anthropic）。"""
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "anthropic",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        desc = payload.get("error_description") or payload.get("error") or f"HTTP {exc.code}: {raw[:200]}"
        raise RuntimeError(f"Anthropic 令牌端点拒绝: {desc}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(
            f"Anthropic 连接失败（{exc.__class__.__name__}）：请检查网络/代理是否能访问 console.anthropic.com"
        ) from exc


def exchange_code(code_with_state: str, code_verifier: str, state: str) -> Dict[str, Any]:
    """用回调页复制的「code#state」串换 token 组。

    返回 {"access_token", "refresh_token", "expires_in"}；state 不匹配直接拒绝。
    """
    code = code_with_state.strip()
    if "#" in code:
        raw_code, raw_state = code.split("#", 1)
        if raw_state != state:
            raise RuntimeError("回调 code 的 state 与本次会话不匹配（请使用本次登录打开的授权页返回的 code）")
        code = raw_code
    payload = _post_json(
        TOKEN_ENDPOINT,
        {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "state": state,
        },
    )
    if not payload.get("access_token"):
        raise RuntimeError(f"换取 token 失败: {payload}")
    return {
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token", ""),
        "expires_in": int(payload.get("expires_in") or 0),
    }


def refresh_tokens(refresh_token: str) -> Dict[str, Any]:
    """刷新 token 组；refresh_token 以响应新值为准（轮换时旧值作兜底）。"""
    payload = _post_json(
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


def read_clipboard() -> str:
    """读系统剪贴板文本（纯外部命令，逐个尝试；全部失败返回空串）。

    走子进程而非 Qt QClipboard：login 钩子运行在后台线程，QClipboard 仅限
    GUI 线程访问。"""
    commands = [
        ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],  # Windows
        ["pbpaste"],  # macOS
        ["xclip", "-selection", "clipboard", "-o"],  # X11
        ["wl-paste"],  # Wayland
    ]
    for cmd in commands:
        try:
            result = subprocess.run(
                cmd, capture_output=True, timeout=5, check=False
            )
            if result.returncode == 0:
                return result.stdout.decode("utf-8", errors="replace").strip()
        except Exception:
            continue
    return ""


def login(
    timeout_sec: float = LOGIN_TIMEOUT,
    poll_interval: float = LOGIN_POLL_INTERVAL,
    open_browser: bool = True,
) -> Dict[str, Any]:
    """完整登录（托管回调 + 剪贴板轮询变体）。

    浏览器打开授权页 → 用户登录授权 → 回调页显示 code → 用户复制（Ctrl+C）
    → 本端轮询剪贴板，检测到含本会话 state 的「code#state」串（state 每次随机
    生成，天然防误触旧剪贴板内容）→ 自动换取 token。

    返回 {"refresh_token", "expires_in"}；超时抛 TimeoutError。
    refresh_token 为长效凭证（存配置 API_KEY 字段），短效 access_token 由
    provider 层按需换取。
    """
    verifier, challenge, state = generate_pkce()
    url = build_authorize_url(challenge, state)
    if open_browser:
        webbrowser.open(url)

    deadline = time.time() + timeout_sec
    code_with_state = ""
    while time.time() < deadline:
        text = read_clipboard()
        match = _CODE_STATE_PATTERN.match(text) if text else None
        if match and match.group(2) == state:
            code_with_state = text
            break
        time.sleep(poll_interval)
    if not code_with_state:
        raise TimeoutError(
            "等待剪贴板中的回调 code 超时：请在授权后复制回调页展示的 code（含 # 后缀的整段）"
        )
    tokens = exchange_code(code_with_state, verifier, state)
    if not tokens["refresh_token"]:
        raise RuntimeError("Anthropic 未返回 refresh_token，请重试登录")
    return {"refresh_token": tokens["refresh_token"], "expires_in": tokens["expires_in"]}
