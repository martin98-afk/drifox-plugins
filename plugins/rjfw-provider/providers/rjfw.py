# -*- coding: utf-8 -*-
"""服务商插件 — 软件服务AI API中转站（s.rjfw.com）。

站点实况（2026-11-27 实测，GPT-福利组 key）：
- Base URL：`https://s.rjfw.com/v1`，OpenAI 兼容，Bearer 认证。站点自述
  「软件服务AI API中转站」（site_subtitle = ZLY-Sub2API，version 2.25.4），
  Key 管理页 `/keys`，注册仅开放 @qq.com 邮箱白名单。
- **按分组售卖，key 只见所属分组的模型**：公开广场 `/api/v1/model-plaza`
  （免鉴权）列 14 个分组 / 7 个平台 / 63 个模型，但拿别组的模型名请求会回
  404 `Model "x" is not supported by any configured account in this group`。
  实测 GPT-福利组（rate 0.028）8 个 gpt 模型全部 200，claude/gemini/grok/
  deepseek/kimi/glm 全 404。因此内置清单只是「未填 key 时的全貌」，真正的
  可用池由 `models_hook` 打 `/v1/models` 按 key 拉取——该接口在余额 >0 时
  返回本组模型，余额为 0 时一律 403 `INSUFFICIENT_BALANCE`。
- 三条入站协议端点都在：`/v1/chat/completions`（实测 200）、`/v1/responses`
  （实测 200）、`/v1/messages`（本组 403 `This group does not allow
  /v1/messages dispatch`——是**分组级开关**，不是协议不存在）。故 claude 系
  按 OpenAI 兼容通道调用，未写 model_adapter：本站是否允许 claude 走 chat
  没有实测样本，等买到 Claude 组 key 再定（报「不支持该接口」时再补 router，
  参考 oaipro-provider）。
- **余额**：`GET /v1/usage` 用 sk- key 直接返回（Bearer，无需网页登录态）：
  `{balance, remaining, unit, isValid, planName, usage.today, usage.total}`。
  本站与 OAIPro 不同，没有绕 Cookie/JWT 的必要。
- 能力实测：`reasoning_effort: "high"` 被接受（200）→ 思考参数按
  reasoning_effort 声明；`image_url` 视觉输入 200；`stream: true` 返回标准
  `chat.completion.chunk` SSE。
- 上游是 Codex 账号池：多数 gpt 模型的 `prompt_tokens` 被注入 4100~5400 token
  的渠道侧系统提示（回复常以 "What would you like me to work on?" 开场），
  按缓存折扣计费；`gpt-6.1-sol` 实测只有 7 token，故设为默认模型。
- 图像与 TTS 模型（gpt-image-2 系列 / gemini-*-image / nano-banana /
  gemini-3.1-flash-tts-preview）不进列表：DriFox 模型下拉用于对话，选中即报错。
models_dev_id 留空：模型名与官方一致，但本站是聚合站，接 models.dev 会把
站外模型灌进「获取模型列表」。
"""
from typing import Any, Dict, List, Optional

from app.plugins.registries.provider_registry import ProviderDef

_SITE_URL = "https://s.rjfw.com"
_API_URL = f"{_SITE_URL}/v1"
_USAGE_URL = f"{_API_URL}/usage"
_MODELS_URL = f"{_API_URL}/models"

# 站点前置 Cloudflare，缺失 UA 的请求可能被挑战
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_GPT_MODELS = [
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-6",
    "gpt-6-astra",
    "gpt-6-sol",
    "gpt-6.1",
    "gpt-6.1-sol",
    "gpt-6.1-terra",
    "gpt-6.2-astra",
    "gpt-6.2-sol",
]
_CLAUDE_MODELS = [
    "claude-fable-5",
    "claude-fable-5-1",
    "claude-fable-5-2",
    "claude-fable-5.1",
    "claude-fable-5.2",
    "claude-haiku-4-5",
    "claude-haiku-5-5",
    "claude-opus-4",
    "claude-opus-4-1",
    "claude-opus-4-5",
    "claude-opus-4-6",
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-opus-5",
    "claude-opus-5-5",
    "claude-sonnet-4",
    "claude-sonnet-4-5",
    "claude-sonnet-4-6",
    "claude-sonnet-5",
    "claude-sonnet-5-5",
]
_GEMINI_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.1-pro",
    "gemini-3.1-pro-preview",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-4-argon",
    "gemini-4-argon-high",
    "gemini-4-carbon",
    "gemini-4-carbon-high",
    "gemini-4-hydrogen",
    "gemini-4-hydrogen-high",
    "gemini-4-neon",
]
_GROK_MODELS = ["grok-4.6", "grok-4.7"]
_DEEPSEEK_MODELS = ["deepseek-v4-pro", "deepseek-v4.1-flash"]
_KIMI_MODELS = ["kimi-k3", "kimi-k3.1-pro"]
_GLM_MODELS = ["glm-5.3", "glm-5.3-flash"]

# 聚合网关能力取旗舰模型的公共交集；reasoning_effort 是 gpt/grok 系的官方语义
_FAMILY_CAPABILITIES = {
    "token_ratio": 1.00,
    "context_limit": 200000,
    "max_output_tokens": 32768,
    "absolute_limit": 200000,
    "supports_vision": True,
    "supports_thinking": True,
    "thinking_param": "reasoning_effort",
    "reasoning_effort_param": "reasoning_effort",
}
# claude 系走 OpenAI 兼容通道时思考参数是另一套语义，未实测前不声明（避免 400）
_CLAUDE_CAPABILITIES = {
    "token_ratio": 1.00,
    "context_limit": 200000,
    "max_output_tokens": 32768,
    "absolute_limit": 200000,
    "supports_vision": True,
    "supports_thinking": False,
}
# 国模（deepseek / kimi / glm）：广场未给窗口，取保守值；视觉与思考均不声明
_CN_MODEL_CAPABILITIES = {
    "token_ratio": 1.00,
    "context_limit": 128000,
    "max_output_tokens": 16384,
    "absolute_limit": 128000,
    "supports_vision": False,
    "supports_thinking": False,
}


def _headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": _UA,
    }


def _is_media_model(model: str) -> bool:
    """图像 / TTS 模型不进对话下拉（选中即报错）。"""
    name = model.lower()
    return (
        "-image" in name
        or "image-" in name
        or "nano-banana" in name
        or "tts" in name
    )


def _fetch_models(config: Dict[str, Any]) -> List[str]:
    """「获取模型列表」：GET /v1/models，返回当前 key 所属分组真实可用的模型。

    分组是本站的核心概念——同一个 API URL 下不同 key 看到不同模型池，
    所以内置清单只是全貌兜底，这里才是权威来源。
    """
    import requests

    api_key = (config.get("API_KEY", "") or "").strip()
    if not api_key:
        raise RuntimeError("请先填入 API Key 再获取模型列表")
    try:
        resp = requests.get(_MODELS_URL, headers=_headers(api_key), timeout=20)
    except Exception as e:
        raise RuntimeError(f"读取模型列表失败：{e}") from e
    if resp.status_code == 401:
        raise RuntimeError("API Key 无效")
    if resp.status_code == 403:
        raise RuntimeError("站点拒绝请求：余额不足或该 Key 被限流，请先充值")
    if resp.status_code != 200:
        raise RuntimeError(f"读取模型列表失败 (HTTP {resp.status_code})")
    try:
        payload = resp.json() or {}
    except Exception as e:
        raise RuntimeError("读取模型列表失败：响应不是 JSON") from e
    items = payload.get("data") if isinstance(payload, dict) else payload
    models = [
        str(item.get("id") or "").strip()
        for item in (items or [])
        if isinstance(item, dict)
    ]
    models = [m for m in models if m and not _is_media_model(m)]
    if not models:
        raise RuntimeError("站点返回空模型列表：当前 Key 所属分组没有可用模型")
    return models


def _fetch_rjfw_balance(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """余额查询：GET /v1/usage（Bearer sk- key，无需登录态）。

    返回：
    - {"balance": float, "currency": "$"}  成功
    - {"hide": True, "tooltip": "..."}    key 失效 / 站点异常
    - None                                 未填 API Key（不请求）
    """
    import requests

    api_key = (config.get("API_KEY", "") or "").strip()
    if not api_key:
        return None
    try:
        resp = requests.get(_USAGE_URL, headers=_headers(api_key), timeout=10)
    except Exception:
        return {"hide": True, "tooltip": "余额查询失败：网络不可达"}
    if resp.status_code == 401:
        return {"hide": True, "tooltip": "API Key 无效"}
    if resp.status_code != 200:
        return {"hide": True, "tooltip": f"余额查询失败 (HTTP {resp.status_code})"}
    try:
        data = resp.json() or {}
    except Exception:
        return {"hide": True, "tooltip": "余额查询异常：响应不是 JSON"}
    if data.get("isValid") is False:
        return {"hide": True, "tooltip": "API Key 已失效"}
    try:
        balance = float(data.get("balance", data.get("remaining")) or 0)
    except (TypeError, ValueError):
        return {"hide": True, "tooltip": "余额字段异常"}
    unit = str(data.get("unit") or "USD").strip().upper()
    currency = "¥" if unit in ("CNY", "RMB") else "$"
    return {"balance": round(balance, 2), "currency": currency}


def register(registry):
    """注册软件服务AI 中转站服务商定义"""
    model_caps = {}
    for model in _CLAUDE_MODELS:
        model_caps[model] = dict(_CLAUDE_CAPABILITIES)
    for model in _DEEPSEEK_MODELS + _KIMI_MODELS + _GLM_MODELS:
        model_caps[model] = dict(_CN_MODEL_CAPABILITIES)
    capabilities = dict(_FAMILY_CAPABILITIES)
    capabilities["models_hook"] = _fetch_models
    registry.register(
        ProviderDef(
            name="软件服务AI",
            icon="rjfw",
            api_url=_API_URL,
            auth_type="bearer",
            # 实测只有 gpt-6.1-sol 无渠道侧系统提示注入（prompt_tokens 7 vs 其他 4~5K）
            default_model="gpt-6.1-sol",
            default_params={
                "温度": 0.7,
                "最大Token": 32768,
            },
            register_url=f"{_SITE_URL}/keys",
            models=(
                _GPT_MODELS
                + _CLAUDE_MODELS
                + _GEMINI_MODELS
                + _GROK_MODELS
                + _DEEPSEEK_MODELS
                + _KIMI_MODELS
                + _GLM_MODELS
            ),
            family="rjfw",
            capabilities=capabilities,
            model_capabilities=model_caps,
            balance_fetcher=_fetch_rjfw_balance,
        )
    )