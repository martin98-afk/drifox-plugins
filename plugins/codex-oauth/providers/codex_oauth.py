# -*- coding: utf-8 -*-
"""服务商插件 — OpenAI Codex（chatgpt.com/backend-api/codex，OAuth 登录制）。

接入形态对齐 GitHub Copilot 先例：
    API Key 字段存长效 refresh_token（config_id 稳定、原生加密链）。
    Authorization 头为可调用值：chat_worker 每次请求传入 llm_config，按
    refresh_token 从本地缓存取短效 access_token（临期 5 分钟自动刷新）。

登录：OAuth Device Flow（codex_auth.login）——弹浏览器打开授权页，
user_code 自动复制到剪贴板，用户粘贴后轮询回填 refresh_token。

协议通道：OpenAI Responses API（POST {base}/responses）。default_params 预置
「使用ResponsesAPI: True」，chat_worker 经 model adapter 判定后走原生 responses
通道（思考内容只在 /v1/responses 返回）。

模型池：/models 端点按 OAuth 凭证拉取（models_hook，账号绑定目录，随订阅
档位而异）；内置列表仅兜底。

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

_API_ENDPOINT = "https://chatgpt.com/backend-api/codex"
_CACHE_DIR = get_app_data_dir() / "codex_oauth" / "cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_REFRESH_SKEW_SEC = 5 * 60  # 剩 5 分钟视为临期（对齐 codex_auth.REFRESH_SKEW_SEC）

_CACHE_LOCK = threading.Lock()
_CACHE: dict = {}  # refresh_token -> {"access_token", "refresh_token", "expires_at", "account_id"}


def _load_auth_module():
    """按路径加载同目录认证模块（providers 目录非包，loader 按文件加载）。"""
    import importlib.util

    auth_path = Path(__file__).with_name("_codex_auth.py")
    spec = importlib.util.spec_from_file_location("codex_oauth_codex_auth", auth_path)
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

    返回 {"access_token", "refresh_token", "expires_at", "account_id"}；
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
        "expires_at": time.time() + float(tokens["expires_in"] or 3600),
        "account_id": tokens["account_id"],
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


def _account_header(llm_config: dict) -> str:
    """动态 ChatGPT-Account-Id 头：与 token 刷新同源取账号 ID；缺失时省略。"""
    refresh_token = str((llm_config or {}).get("API_KEY", "") or "").strip()
    if not refresh_token:
        return ""
    try:
        return _exchange_access_token(refresh_token)["account_id"] or ""
    except Exception:
        return ""


# 伪装头：originator / UA 为 Codex CLI 客户端标识；Authorization /
# ChatGPT-Account-Id 为可调用值（chat_worker 每请求传入 llm_config 按配置取）。
_EXTRA_HEADERS = {
    "Authorization": _auth_header,
    "ChatGPT-Account-Id": _account_header,
    "originator": "codex_cli_rs",
    "User-Agent": "codex_cli_rs/0.62.0 (Windows 11; x86_64) DriFox",
}


def _auto_login():
    """登录钩子（编辑卡后台线程调用）：Device Flow 授权，回填长效 refresh_token。"""
    from loguru import logger

    ca = _load_auth_module()
    logger.info("[OpenAI Codex] 发起 Device Flow 登录（请求 auth.openai.com 设备码）")
    try:
        result = ca.login(timeout_sec=600)
    except Exception as e:
        logger.warning(f"[OpenAI Codex] 登录失败: {e}")
        raise
    refresh_token = result["refresh_token"]
    logger.info("[OpenAI Codex] 授权成功，预热短效 access_token")
    # 预热：立即刷新一次，保存配置后立即可聊天
    _exchange_access_token(refresh_token)
    info = (
        "登录成功（ChatGPT）：API Key 为长效 refresh_token，聊天自动换取短效 "
        "access_token；user_code 已复制到剪贴板"
    )
    return {"api_key": refresh_token, "info": info + "，API Key 已回填请保存"}


# 内置模型池（2026-10 ChatGPT 登录通道现役；gpt-5.x 已于 2026-08/10 陆续退役）。
# 实际可用性随订阅档位而异（Free/Go 走 luna 系，Plus/Pro 走 sol 系）。
# 兜底专用：权威池以 models_hook 拉取的 /models 为准。
_MODELS = [
    "gpt-6.1-sol",
    "gpt-6-sol",
    "gpt-6.1-luna",
    "gpt-6-luna",
]


def _ranked_slugs(entries) -> list:
    """从目录 models 列表取可见 slug：跳过 visibility=hide/hidden，
    按 (priority, slug) 排序去重。不按 supported_in_api 过滤——该标记描述
    公开 API 可用性，Codex OAuth 通道对标记为 False 的 slug 仍接受。"""
    sortable = []
    for item in entries if isinstance(entries, list) else []:
        if not isinstance(item, dict):
            continue
        slug = str(item.get("slug", "") or "").strip()
        if not slug:
            continue
        if str(item.get("visibility", "") or "").strip().lower() in ("hide", "hidden"):
            continue
        try:
            priority = int(item.get("priority"))
        except (TypeError, ValueError):
            priority = 10000
        sortable.append((priority, slug))
    sortable.sort()
    return list(dict.fromkeys(slug for _, slug in sortable))


def _fetch_models(config):
    """模型列表获取钩子：按本配置的 rt 换 token 拉 /models（权威池，随订阅而异）。

    端点契约（对齐 hermes-agent 实测）：
    - GET {base}/models?client_version=<v>，先 99.0.0 再 0.0.0（ungated 哨兵），
      第一个返回 200 且 models 非空的胜出；
    - 必须带 ChatGPT-Account-Id，否则 HTTP 200 但 {"models": []} 伪装成无模型。
    """
    refresh_token = str((config or {}).get("API_KEY", "") or "").strip()
    if not refresh_token:
        raise RuntimeError("尚未登录：请先点击「登录」")
    entry = _exchange_access_token(refresh_token)
    headers = {
        "Authorization": f"Bearer {entry['access_token']}",
        "Accept": "application/json",
        "User-Agent": "codex_cli_rs/0.62.0 (Windows 11; x86_64) DriFox",
    }
    if entry.get("account_id"):
        headers["ChatGPT-Account-Id"] = entry["account_id"]
    models: list = []
    for client_version in ("99.0.0", "0.0.0"):
        req = urllib.request.Request(
            f"{_API_ENDPOINT}/models?client_version={client_version}", headers=headers
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        entries = (payload.get("models") or []) if isinstance(payload, dict) else []
        models = _ranked_slugs(entries)
        if models:
            break
    return models or list(_MODELS)


def register(registry):
    registry.register(
        ProviderDef(
            name="OpenAI Codex",
            icon="OpenAI",
            api_url=_API_ENDPOINT,
            auth_type="bearer",
            default_model="gpt-6.1-sol",
            default_params={
                # Codex 通道为 Responses API 形态（POST {base}/responses），
                # chat/completions 形态不被 backend 接受，必须显式开启
                "使用ResponsesAPI": True,
                "最大Token": 32768,
            },
            register_url="https://chatgpt.com/#pricing",
            models=_MODELS,
            family="openai",
            capabilities={
                "extra_headers": _EXTRA_HEADERS,
                "login_hook": _auto_login,
                "models_hook": _fetch_models,
                # 设备码页强制手输 code（不认 URL 预填），告知 code 已在剪贴板
                "login_hint": "已打开 OpenAI 授权页，user_code 已复制到剪贴板：粘贴后点 Continue（最长等待 10 分钟）",
                "context_limit": 272000,
                "max_output_tokens": 128000,
                "absolute_limit": 128000,
                "supports_vision": True,
                "supports_thinking": True,
            },
        )
    )
