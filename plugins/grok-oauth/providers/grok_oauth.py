# -*- coding: utf-8 -*-
"""服务商插件 — xAI Grok（cli-chat-proxy.grok.com/v1，OAuth 登录制）。

接入形态对齐 anthropic-oauth / codex-oauth 先例：
    API Key 字段存长效 refresh_token（config_id 稳定、原生加密链）。
    Authorization 头为可调用值：chat_worker 每次请求传入 llm_config，按
    refresh_token 从本地缓存取短效 access_token（临期自动刷新）。

登录：xAI OAuth + PKCE（grok_auth.login）——本端起 127.0.0.1:56121 临时回调
服务，弹浏览器打开 auth.x.ai 授权页，用户授权后自动回传授权码换 token，
全程无需手动复制。

协议通道：xAI Responses API（POST {base}/responses）。default_params 预置
「使用ResponsesAPI: True」，chat_worker 经 model adapter 判定后走原生
responses 通道（与 codex-oauth 同款；OAuth 订阅额度仅 .cli 代理通道接受，
api.x.ai/v1 为 API Key 专用）。

模型池：/v1/models-v2 按 OAuth 凭证拉取（models_hook，账号绑定目录，随订阅
而异）；内置列表仅兜底。

风险提示：非官方客户端协议实现，存在违反服务条款与封号风险，自行评估。
"""
import hashlib
import json
import threading
import time
import urllib.request
from pathlib import Path

from app.plugins.registries.provider_registry import ProviderDef
from app.utils.utils import get_app_data_dir

# OAuth 订阅通道（.cli 代理）；api.x.ai/v1 仅接受 API Key，不用于本插件
_API_ENDPOINT = "https://cli-chat-proxy.grok.com/v1"
_CACHE_DIR = get_app_data_dir() / "grok_oauth" / "cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_REFRESH_SKEW_SEC = 5 * 60  # 剩 5 分钟视为临期

_CACHE_LOCK = threading.Lock()
_CACHE: dict = {}  # refresh_token -> {"access_token", "refresh_token", "expires_at"}


def _load_auth_module():
    """按路径加载同目录认证模块（providers 目录非包，loader 按文件加载）。"""
    import importlib.util

    auth_path = Path(__file__).with_name("_grok_auth.py")
    spec = importlib.util.spec_from_file_location("grok_oauth_grok_auth", auth_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载认证模块: {auth_path}")
    ca = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ca)
    return ca


def _cache_path(refresh_token: str) -> Path:
    digest = hashlib.sha1(refresh_token.encode("utf-8")).hexdigest()[:12]
    return _CACHE_DIR / f"{digest}.json"


def _cache_get(refresh_token: str) -> dict:
    with _CACHE_LOCK:
        if refresh_token in _CACHE:
            return _CACHE[refresh_token]
    try:
        entry = json.loads(_cache_path(refresh_token).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        entry = {}
    with _CACHE_LOCK:
        _CACHE[refresh_token] = entry
    return entry


def _cache_put(refresh_token: str, entry: dict) -> None:
    with _CACHE_LOCK:
        _CACHE[refresh_token] = entry
    _cache_path(refresh_token).write_text(json.dumps(entry), encoding="utf-8")


def _exchange_access_token(refresh_token: str) -> dict:
    """按 rt 取可用 token 组：缓存命中（未临期）直接返回，否则刷新。

    返回 {"access_token", "refresh_token", "expires_at"}；
    刷新后 refresh_token 可能轮换，缓存以新值为准（配置里旧 rt 仅作冷启动兜底，
    轮换后若缓存丢失需重新登录——与 CodeBuddy rt 轮换同款已知权衡）。
    """
    entry = _cache_get(refresh_token)
    if entry.get("access_token") and entry.get("expires_at", 0) > time.time() + _REFRESH_SKEW_SEC:
        return entry
    ca = _load_auth_module()
    tokens = ca.refresh_tokens(refresh_token)
    new_entry = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        # xAI 未公开 access_token 寿命文档，缺省按 1 小时计（临期自动刷新兜底）
        "expires_at": time.time() + float(tokens["expires_in"] or 3600),
    }
    _cache_put(refresh_token, new_entry)
    return new_entry


def _auth_header(llm_config: dict) -> str:
    """动态 Authorization 头：按当前配置的 API_KEY（rt）换取短效 access_token。"""
    refresh_token = str((llm_config or {}).get("API_KEY", "") or "").strip()
    if not refresh_token:
        return ""
    try:
        return f"Bearer {_exchange_access_token(refresh_token)['access_token']}"
    except Exception:
        return ""  # 换取失败回退空头（报错由请求层透出）


# UA 与 Grok CLI 对齐（.cli 代理通道社区实践）；Authorization 为可调用值
# （chat_worker 每请求传入 llm_config 按配置取）。
_EXTRA_HEADERS = {
    "Authorization": _auth_header,
    "User-Agent": "grok-cli/1.0 (DriFox)",
}


def _auto_login():
    """登录钩子（编辑卡后台线程调用）：本地回调授权，回填长效 refresh_token。"""
    from loguru import logger

    ca = _load_auth_module()
    logger.info("[Grok OAuth] 打开 auth.x.ai 授权页，等待本地回调 127.0.0.1:56121")
    try:
        result = ca.login(timeout_sec=600)
    except Exception as e:
        logger.warning(f"[Grok OAuth] 登录失败: {e}")
        raise
    refresh_token = result["refresh_token"]
    logger.info("[Grok OAuth] 授权成功，预热短效 access_token")
    # 预热：立即刷新一次，保存配置后立即可聊天
    _exchange_access_token(refresh_token)
    info = (
        "登录成功（Grok）：API Key 为长效 refresh_token，聊天自动换取短效 "
        "access_token"
    )
    return {"api_key": refresh_token, "info": info + "，API Key 已回填请保存"}


def _fetch_models(config):
    """模型列表获取钩子：按本配置的 rt 换 token 拉 /v1/models-v2（账号绑定目录）。"""
    refresh_token = str((config or {}).get("API_KEY", "") or "").strip()
    if not refresh_token:
        raise RuntimeError("尚未登录：请先点击「登录」")
    token = _exchange_access_token(refresh_token)["access_token"]
    req = urllib.request.Request(
        f"{_API_ENDPOINT}/models-v2",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "grok-cli/1.0 (DriFox)",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return _extract_model_ids(payload) or list(_MODELS)


def _extract_model_ids(payload) -> list:
    """宽松解析 models-v2 响应：优先 data[].id，兼容 models[].id 与裸字符串数组。"""
    items = []
    if isinstance(payload, dict):
        items = payload.get("data") or payload.get("models") or []
    elif isinstance(payload, list):
        items = payload
    out = []
    for x in items if isinstance(items, list) else []:
        mid = x.get("id") if isinstance(x, dict) else x
        if isinstance(mid, str) and mid.startswith("grok"):
            out.append(mid)
    return out


# 内置兜底（权威池以 models_hook 拉取的账号绑定目录为准）
_MODELS = [
    "grok-4.7",
    "grok-4.6",
    "grok-4.3",
    "grok-4-fast",
]


def register(registry):
    registry.register(
        ProviderDef(
            name="Grok OAuth",
            icon="Grok",
            api_url=_API_ENDPOINT,
            auth_type="bearer",
            default_model="grok-4.7",
            default_params={
                # Grok 订阅通道为 Responses API 形态（POST {base}/responses），
                # chat/completions 形态不被 .cli 代理接受，必须显式开启
                "使用ResponsesAPI": True,
                "最大Token": 32768,
            },
            register_url="https://x.ai/grok",
            models=_MODELS,
            models_dev_id="xai",
            family="openai",
            capabilities={
                "extra_headers": _EXTRA_HEADERS,
                "login_hook": _auto_login,
                # 本端起 127.0.0.1:56121 回调服务，浏览器授权后自动完成
                "login_hint": "已打开 xAI 授权页：登录 SuperGrok / X Premium+ 账号并授权，DriFox 会自动接收回调完成登录（最长等待 10 分钟，期间请勿关闭授权页）",
                "context_limit": 500000,
                "max_output_tokens": 32768,
                "absolute_limit": 32768,
                "supports_vision": True,
                "supports_thinking": True,
            },
        )
    )
