# -*- coding: utf-8 -*-
"""xAI (Grok) 认证客户端 — OAuth 2.0 + PKCE 登录 / 刷新（纯标准库）。

协议来源：xAI 官方 OIDC 端点（auth.x.ai/.well-known/openid-configuration），
客户端参数与 Grok CLI / OpenCode / pi-xai-oauth 等公开实现一致（2026-10 校准）：

- 授权端点   https://auth.x.ai/oauth2/authorize
- 令牌端点   https://auth.x.ai/oauth2/token
- 设备端点   https://auth.x.ai/oauth2/device/code（本插件未用：桌面端走本地回调）
- 回调地址   http://127.0.0.1:56121/callback（官方 client 注册的 loopback 端口，
             Grok CLI 同款；本端起临时 HTTP 服务自动接收授权码）
- client_id  b1a00492-073a-47ea-816f-4c329264a828（公开 OAuth client 标识）
- PKCE       S256；state 每次随机生成，绑定本会话回调
- scope      openid profile email offline_access grok-cli:access api:access
             conversations:read conversations:write（与 Grok CLI 完全一致，
             保障订阅权益判定）

登录流程（本地 loopback 回调变体）：
    起 127.0.0.1:56121 临时 HTTP 服务 → 浏览器打开授权页 → 用户登录授权 →
    xAI 302 回本端 /callback?code=...&state=... → 校验 state → 用 code +
    code_verifier 换 token 组 → 回调页返回成功提示。

刷新：同端点 grant_type=refresh_token（access/refresh 均可能轮换，以响应新值为准）。

令牌端点请求：标准 OAuth2 form 表单（application/x-www-form-urlencoded）。

API 调用（OAuth 凭证走订阅通道，与 api.x.ai/v1 的 API Key 通道不同）：
    POST https://cli-chat-proxy.grok.com/v1/responses（Responses API 形态）
    Authorization: Bearer <access_token>

风险提示：非官方客户端协议实现，存在违反服务条款与封号风险，请自行评估。
"""
import base64
import hashlib
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional

AUTHORIZE_ENDPOINT = "https://auth.x.ai/oauth2/authorize"
TOKEN_ENDPOINT = "https://auth.x.ai/oauth2/token"
REDIRECT_HOST = "127.0.0.1"
REDIRECT_PORT = 56121
REDIRECT_PATH = "/callback"
REDIRECT_URI = f"http://{REDIRECT_HOST}:{REDIRECT_PORT}{REDIRECT_PATH}"

# Grok CLI 的公开 OAuth client_id（社区实现通用值）
CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
SCOPE = (
    "openid profile email offline_access grok-cli:access "
    "api:access conversations:read conversations:write"
)

DEFAULT_TIMEOUT = 30.0
LOGIN_TIMEOUT = 600.0

_SUCCESS_HTML = (
    "<!doctype html><html lang=\"zh\"><meta charset=\"utf-8\">"
    "<title>DriFox 登录成功</title>"
    "<body style=\"font-family:system-ui;display:flex;align-items:center;"
    "justify-content:center;height:100vh;margin:0\">"
    "<div style=\"text-align:center\"><h2>✅ 授权成功</h2>"
    "<p>token 已送达 DriFox，本页可以关闭。</p></div></body></html>"
)


def generate_pkce() -> tuple:
    """生成 (code_verifier, code_challenge, state)，RFC 7636 标准三件套。"""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    state = base64.urlsafe_b64encode(secrets.token_bytes(24)).rstrip(b"=").decode("ascii")
    return verifier, challenge, state


def build_authorize_url(code_challenge: str, state: str) -> str:
    """构造授权页 URL。"""
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    return f"{AUTHORIZE_ENDPOINT}?{urllib.parse.urlencode(params)}"


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
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        desc = payload.get("error_description") or payload.get("error") or f"HTTP {exc.code}: {raw[:200]}"
        raise RuntimeError(f"xAI 令牌端点拒绝: {desc}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(
            f"xAI 连接失败（{exc.__class__.__name__}）：请检查网络/代理是否能访问 auth.x.ai"
        ) from exc


def exchange_code(code: str, code_verifier: str) -> Dict[str, Any]:
    """用授权码 + PKCE verifier 换 token 组。

    返回 {"access_token", "refresh_token", "expires_in"}。
    """
    payload = _post_form(
        TOKEN_ENDPOINT,
        {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
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


class _CallbackServer:
    """一次性 loopback 回调服务器：收到匹配 state 的授权码后自动关闭。"""

    def __init__(self, expected_state: str):
        self.expected_state = expected_state
        self.code: Optional[str] = None
        self.error: Optional[str] = None
        self._done = threading.Event()
        self._httpd: Optional[HTTPServer] = None

        server = self

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802（BaseHTTPRequestHandler 命名约定）
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path != REDIRECT_PATH:
                    self.send_response(404)
                    self.end_headers()
                    return
                query = urllib.parse.parse_qs(parsed.query)
                if "error" in query:
                    server.error = query["error"][0]
                else:
                    code = (query.get("code") or [""])[0]
                    state = (query.get("state") or [""])[0]
                    if state == server.expected_state and code:
                        server.code = code
                    else:
                        server.error = "回调 code/state 校验失败（请用本次登录打开的授权页完成授权）"
                body = _SUCCESS_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                server._done.set()

            def log_message(self, *args):  # 静默访问日志
                pass

        self._handler_cls = _Handler

    def serve_once(self, timeout_sec: float) -> Optional[str]:
        """阻塞等待回调，返回授权码；超时/出错抛异常。"""
        try:
            self._httpd = HTTPServer((REDIRECT_HOST, REDIRECT_PORT), self._handler_cls)
        except OSError as exc:
            raise RuntimeError(
                f"本地回调端口 {REDIRECT_PORT} 不可用（{exc}）：请关闭占用该端口的程序"
                "（Grok CLI / OpenCode 等登录时也用它）后重试"
            ) from exc
        self._httpd.timeout = 1.0  # 单次 select 粒度，保证能响应关闭
        deadline = time.time() + timeout_sec
        try:
            while not self._done.is_set():
                if time.time() >= deadline:
                    raise TimeoutError(
                        f"等待浏览器授权超时（{int(timeout_sec)} 秒）：请重新登录并在 "
                        f"{int(timeout_sec / 60)} 分钟内完成授权"
                    )
                self._httpd.handle_request()
            if self.error:
                raise RuntimeError(f"xAI 授权失败: {self.error}")
            if not self.code:
                raise RuntimeError("xAI 回调未返回授权码，请重试登录")
            return self.code
        finally:
            self._httpd.server_close()


def login(timeout_sec: float = LOGIN_TIMEOUT, open_browser: bool = True) -> Dict[str, Any]:
    """完整登录（本地 loopback 回调变体）。

    浏览器打开 auth.x.ai 授权页 → 用户登录（SuperGrok / X Premium+ 账号）并
    授权 → xAI 302 回 127.0.0.1:56121/callback → 本端自动收码换取 token。

    返回 {"refresh_token", "expires_in"}；超时抛 TimeoutError。
    refresh_token 为长效凭证（存配置 API_KEY 字段），短效 access_token 由
    provider 层按需换取。
    """
    verifier, challenge, state = generate_pkce()
    url = build_authorize_url(challenge, state)
    server = _CallbackServer(state)
    # 先起服务器再开浏览器：避免 302 回调早于监听（浏览器打开本身耗时足够，
    # 但顺序正确没有代价）
    if open_browser:
        webbrowser.open(url)
    code = server.serve_once(timeout_sec)
    tokens = exchange_code(code, verifier)
    if not tokens["refresh_token"]:
        raise RuntimeError("xAI 未返回 refresh_token（scope 缺失 offline_access？），请重试登录")
    return {"refresh_token": tokens["refresh_token"], "expires_in": tokens["expires_in"]}
