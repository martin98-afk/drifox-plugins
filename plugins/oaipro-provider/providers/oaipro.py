# -*- coding: utf-8 -*-
"""服务商插件 — OAIPro 中转站（api.oaipro.com）。

站点实况（2026-11-16 实测，Neo API 闭源二开，版本 2026.4.1）：
- Base URL：`https://api.oaipro.com/v1`，OpenAI 兼容，Bearer 认证
- **协议按模型硬分流**（这是本插件存在的原因）：
    * gpt-4o / 4.1 / 5.x（非 pro）/ 6.x / o3 / chat-latest → 仅 `/v1/chat/completions`
    * gpt-5-pro / 5.x-pro / 5.3-codex / o3-pro → 仅 `/v1/responses`
    * claude-* → 仅 `/v1/messages`（打 chat/completions 报 403）
  路由由同插件的 model_adapters/oaipro_router.py 决定；anthropic 通道由
  宿主 system-transports ≥1.1.0 提供（transports/anthropic_messages.py）。
- **余额**：站点没有任何 API key 级余额接口。`/v1/dashboard/billing/*`、
  `/api/user/self`、`/api/usage/token`（new-api 系）全部 404；唯一可用的是
  `/backend-api/users/me`，需要网页登录态。登录 `POST /backend-api/sessions`
  强制 Turnstile 人机验证，脚本无法自动登录 → 只能让用户粘贴浏览器 Cookie。
- 余额字段：`user.quota`（内部额度单位），换算 `quota_per_unit`（本站 500000）得美元。
  该值从公开的 `/backend-api/status` 读取，站点调整单位时自动跟随。

单条服务商承载全部模型（GPT + Claude 混列）：一条配置一个 Key，协议分流对
用户透明。能力声明分两层——family 级给 GPT 语义（reasoning_effort），
`model_capabilities` 给 claude 系逐模型覆盖成 Anthropic 语义（thinking budget）。
models_dev_id 留空：模型名虽与官方一致，但合并 models.dev 表会把站外模型
灌进「获取模型列表」。
"""

from typing import Any, Dict, List, Optional

from app.plugins.registries.provider_registry import ProviderDef, QuotaField

_API_URL = "https://api.oaipro.com/v1"
_SITE_URL = "https://api.oaipro.com"
_STATUS_URL = f"{_SITE_URL}/backend-api/status"
_ME_URL = f"{_SITE_URL}/backend-api/users/me"

# 本站默认额度单位（status 读不到时兜底；实测值 500000）
_DEFAULT_QUOTA_PER_UNIT = 500000

# 走 chat/completions 实测 200 的模型（.tmp 实测记录，2026-11-16）
_GPT_MODELS: List[str] = [
    "gpt-6.1-sol",
    "gpt-6-sol",
    "gpt-6-luna",
    "gpt-6-astra",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
    "gpt-5.5",
    "gpt-5.5-2026-04-23",
    "gpt-5.4",
    "gpt-5.4-2026-03-05",
    "gpt-5.4-mini",
    "gpt-5.4-mini-2026-03-17",
    "gpt-5.4-nano",
    "gpt-5.4-nano-2026-03-17",
    "gpt-5.2",
    "gpt-5.2-2025-12-11",
    "gpt-5.1",
    "gpt-5.1-2025-11-13",
    "gpt-5",
    "gpt-5-2025-08-07",
    "gpt-5-mini",
    "gpt-5-mini-2025-08-07",
    "gpt-5-nano",
    "gpt-5-nano-2025-08-07",
    "gpt-4.1",
    "gpt-4.1-2025-04-14",
    "gpt-4.1-mini",
    "gpt-4.1-mini-2025-04-14",
    "gpt-4o",
    "gpt-4o-2024-11-20",
    "gpt-4o-2024-08-06",
    "gpt-4o-mini",
    "gpt-4o-mini-2024-07-18",
    "chat-latest",
    "o3",
    "o3-2025-04-16",
]

# 只能走 /v1/responses 的模型（打 chat/completions 会 404 提示换端点）
_RESPONSES_ONLY_MODELS: List[str] = [
    "gpt-5.5-pro",
    "gpt-5.5-pro-2026-04-23",
    "gpt-5.4-pro",
    "gpt-5.4-pro-2026-03-05",
    "gpt-5.3-codex",
    "gpt-5.2-pro",
    "gpt-5.2-pro-2025-12-11",
    "gpt-5-pro",
    "gpt-5-pro-2025-10-06",
    "o3-pro",
    "o3-pro-2025-06-10",
]

# 只能走 /v1/messages 的 Claude 模型
_CLAUDE_MODELS: List[str] = [
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-opus-4-5-20251101",
    "claude-sonnet-5-5",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
    "claude-sonnet-4-5-20250929",
    "claude-haiku-5-5",
    "claude-haiku-4-5-20251001",
    "claude-fable-5-1",
    "claude-fable-5",
]

# 会话含图片时 Anthropic 协议用 base64 直传；网关按模型真实能力处理
_CLAUDE_CAPABILITIES = {
    "context_limit": 200000,
    "max_output_tokens": 32000,
    "absolute_limit": 200000,
    "supports_vision": True,
    "supports_thinking": True,
    "thinking_param": "thinking",
    "thinking_budget_param": "thinking_budget",
}

# GPT 系走宿主 openai_chat / openai_responses 通道，思考参数是 reasoning_effort
_GPT_CAPABILITIES = {
    "context_limit": 400000,
    "max_output_tokens": 32768,
    "absolute_limit": 128000,
    "supports_vision": True,
    "supports_thinking": True,
    "thinking_param": "reasoning_effort",
    "reasoning_effort_param": "reasoning_effort",
}


def _write_cookie_from_browser() -> Dict[str, Any]:
    """登录钩子：提示用户从浏览器复制 Cookie（站点强制 Turnstile，无法脚本登录）。"""
    hint = (
        "OAIPro 登录强制人机验证，脚本无法自动登录。请：\n"
        "1) 浏览器打开 https://api.oaipro.com 并登录\n"
        "2) F12 → Network → 任选一个 backend-api 请求 → 复制请求头里的 Cookie\n"
        "3) 粘贴到「套餐用量查询」里的 Cookie 字段（需整行粘贴）\n"
        "余额查询只依赖这个 Cookie，与聊天用的 API Key 无关。"
    )
    return {"api_key": "", "info": hint}


def _fetch_quota_per_unit(timeout: float = 10.0) -> float:
    """站点额度单位（公开接口，无需鉴权）；失败回退内置实测值。"""
    import requests

    try:
        resp = requests.get(_STATUS_URL, timeout=timeout)
        if resp.status_code != 200:
            return float(_DEFAULT_QUOTA_PER_UNIT)
        data = (resp.json() or {}).get("data") or {}
        unit = float(data.get("quota_per_unit") or 0)
        return unit if unit > 0 else float(_DEFAULT_QUOTA_PER_UNIT)
    except Exception:
        return float(_DEFAULT_QUOTA_PER_UNIT)


def _fetch_oaipro_balance(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """余额查询：用网页 Cookie 调 `/backend-api/users/me`，quota → 美元。

    返回：
    - {"balance": float, "currency": "$"}   成功
    - {"hide": True, "tooltip": "..."}      Cookie 缺失/过期/站点异常
    - None                                  未配置 Cookie（不请求）
    """
    import requests

    cookie = str((config or {}).get("cookie", "") or "").strip()
    if not cookie:
        return None

    headers = {
        "Cookie": cookie,
        "Accept": "application/json",
        # 站点对缺失 UA 的请求会走 Cloudflare 挑战，带常规 UA 才直出 JSON
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Referer": f"{_SITE_URL}/api-keys",
    }
    try:
        resp = requests.get(_ME_URL, headers=headers, timeout=15)
    except Exception:
        return {"hide": True, "tooltip": "余额查询失败：网络不可达"}

    if resp.status_code == 401:
        return {"hide": True, "tooltip": "Cookie 已失效，请重新从浏览器复制"}
    if resp.status_code != 200:
        return {"hide": True, "tooltip": f"余额查询失败 (HTTP {resp.status_code})"}

    try:
        payload = resp.json() or {}
    except Exception:
        return {"hide": True, "tooltip": "余额查询异常：响应不是 JSON"}
    if not payload.get("success"):
        message = str(payload.get("message") or "").strip()
        if "登录" in message or "无权" in message:
            return {"hide": True, "tooltip": "Cookie 已失效，请重新从浏览器复制"}
        return {"hide": True, "tooltip": message or "余额查询失败"}
    user = payload.get("data") or {}
    try:
        raw_quota = float(user.get("quota") or 0)
    except (TypeError, ValueError):
        return {"hide": True, "tooltip": "余额字段异常"}

    unit = _fetch_quota_per_unit()
    balance = raw_quota / unit if unit > 0 else raw_quota
    return {"balance": round(balance, 2), "currency": "$"}


# 套餐用量额外字段：Cookie（网页登录态；余额查询用，不进任何模型请求）
_QUOTA_FIELDS = [
    QuotaField(
        key="cookie",
        label="Cookie:",
        placeholder="浏览器 F12 复制整行 Cookie（OAIPro 强制人机验证，需手动粘贴）",
    )
]


def register(registry):
    """注册单条服务商：GPT + Claude 混列，协议分流对用户透明。"""
    registry.register(
        ProviderDef(
            name="OAIPro",
            icon="oaipro",
            api_url=_API_URL,
            auth_type="bearer",
            default_model="gpt-5.4-mini",
            default_params={"温度": 0.7, "最大Token": 200000},
            register_url="https://api.oaipro.com/token",
            models=_GPT_MODELS + _RESPONSES_ONLY_MODELS + _CLAUDE_MODELS,
            family="oaipro",
            capabilities=_GPT_CAPABILITIES,
            # claude 系逐模型覆盖为 Anthropic 能力语义（per-model 声明优先级最高，
            # 高于 family 与 models.dev）：thinking 参数是 budget 而非 effort
            model_capabilities={model: dict(_CLAUDE_CAPABILITIES) for model in _CLAUDE_MODELS},
            extra_quota_fields=_QUOTA_FIELDS,
            balance_fetcher=_fetch_oaipro_balance,
        )
    )
