# -*- coding: utf-8 -*-
"""服务商插件 — Anthropic Claude（api.anthropic.com/v1，OAuth 登录制）。

接入形态对齐 GitHub Copilot 先例：
    API Key 字段存长效 refresh_token（config_id 稳定、原生加密链）。
    Authorization 头为可调用值：chat_worker 每次请求传入 llm_config，按
    refresh_token 从本地缓存取短效 access_token（临期自动刷新）。

登录：Claude Code OAuth（claude_auth.login）——弹浏览器打开 claude.ai 授权页，
用户授权后回调页展示 code，复制后 DriFox 轮询剪贴板自动换取 token。

请求通道：api.anthropic.com/v1 的 OpenAI 兼容层（/chat/completions），与内置
「Anthropic (Claude)」插件同端点；差异仅在凭证——OAuth 凭证必须带
anthropic-beta: oauth-2025-04-20 头（社区实践，非官方兼容层承诺，若 401 见
README「已知限制」）。

模型池：/v1/models 端点按 OAuth 凭证拉取（models_hook，随订阅而异）；内置
列表仅兜底。

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

_API_ENDPOINT = "https://api.anthropic.com/v1"
_CACHE_DIR = get_app_data_dir() / "anthropic_oauth" / "cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_REFRESH_SKEW_SEC = 5 * 60  # 剩 5 分钟视为临期

_CACHE_LOCK = threading.Lock()
_CACHE: dict = {}  # refresh_token -> {"access_token", "refresh_token", "expires_at"}


def _load_auth_module():
    """按路径加载同目录认证模块（providers 目录非包，loader 按文件加载）。"""
    import importlib.util

    auth_path = Path(__file__).with_name("_claude_auth.py")
    spec = importlib.util.spec_from_file_location("anthropic_oauth_claude_auth", auth_path)
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

    返回 {"access_token", "refresh_token", "expires_at"}；刷新后 refresh_token
    可能轮换，缓存以新值为准（配置里旧 rt 仅作冷启动兜底，轮换后若缓存丢失
    需重新登录——与 CodeBuddy rt 轮换同款已知权衡）。
    """
    entry = _cache_get(refresh_token)
    if entry.get("access_token") and entry.get("expires_at", 0) > time.time() + _REFRESH_SKEW_SEC:
        return entry
    ca = _load_auth_module()
    tokens = ca.refresh_tokens(refresh_token)
    new_entry = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        # OAuth access_token 无官方公开寿命文档，实测缺省按 1 小时计
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


# OAuth 凭证请求头（区别于 API Key 路径的三件套）：
#   Authorization 为可调用值（chat_worker 每请求传入 llm_config 按配置取）；
#   anthropic-beta 的 oauth-2025-04-20 为 OAuth 凭证必需；
#   UA / x-app 伪装 Claude Code CLI（社区实践）。
_EXTRA_HEADERS = {
    "Authorization": _auth_header,
    "anthropic-beta": "oauth-2025-04-20",
    "x-app": "cli",
    "User-Agent": "claude-cli/2.0.14 (external, cli)",
}


def _auto_login():
    """登录钩子（编辑卡后台线程调用）：授权 + 剪贴板轮询，回填长效 refresh_token。"""
    from loguru import logger

    ca = _load_auth_module()
    logger.info("[Anthropic OAuth] 打开 claude.ai 授权页，轮询剪贴板等待回调 code")
    try:
        result = ca.login(timeout_sec=300)
    except Exception as e:
        logger.warning(f"[Anthropic OAuth] 登录失败: {e}")
        raise
    refresh_token = result["refresh_token"]
    logger.info("[Anthropic OAuth] 授权成功，预热短效 access_token")
    # 预热：立即刷新一次，保存配置后立即可聊天
    _exchange_access_token(refresh_token)
    info = (
        "登录成功（Claude）：API Key 为长效 refresh_token，聊天自动换取短效 "
        "access_token"
    )
    return {"api_key": refresh_token, "info": info + "，API Key 已回填请保存"}


def _fetch_models(config):
    """模型列表获取钩子：按本配置的 rt 换 token 拉 /v1/models（权威池，随订阅而异）。"""
    refresh_token = str((config or {}).get("API_KEY", "") or "").strip()
    if not refresh_token:
        raise RuntimeError("尚未登录：请先点击「登录」")
    ca = _load_auth_module()
    token = _exchange_access_token(refresh_token)["access_token"]
    req = urllib.request.Request(
        f"{_API_ENDPOINT}/models",
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    items = (payload.get("data") or []) if isinstance(payload, dict) else []
    out = [x["id"] for x in items if isinstance(x, dict) and str(x.get("id", "")).startswith("claude")]
    return out or list(_MODELS)


# 内置兜底（权威池以 models_hook 拉取的 /v1/models 为准）
_MODELS = [
    "claude-sonnet-4-5",
    "claude-haiku-4-5",
    "claude-opus-4-1",
]


def register(registry):
    registry.register(
        ProviderDef(
            name="Anthropic OAuth",
            icon="Anthropic",
            api_url=_API_ENDPOINT,
            auth_type="bearer",
            default_model="claude-sonnet-4-5",
            default_params={"温度": 1.0, "最大Token": 32000},
            register_url="https://claude.ai/#pricing",
            models=_MODELS,
            models_dev_id="anthropic",
            family="anthropic",
            capabilities={
                "extra_headers": _EXTRA_HEADERS,
                "login_hook": _auto_login,
                "models_hook": _fetch_models,
                # 托管回调无本地回传通道：code 由用户复制，本端轮询剪贴板接力
                "login_hint": "已打开 Claude 授权页：登录授权后，回调页会展示一串 code，复制它（Ctrl+C）即可，DriFox 会自动检测并完成登录（最长等待 5 分钟）",
                "context_limit": 200000,
                "max_output_tokens": 8192,
                "absolute_limit": 65536,
                "supports_vision": True,
                "supports_thinking": True,
                "thinking_param": "thinking",
            },
        )
    )
