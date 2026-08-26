# -*- coding: utf-8 -*-
"""
服务商插件 — OpenRouter

数据全部由本插件声明：icon / API URL / 默认参数 / 模型列表 /
models.dev 映射 / family 能力 / 余额查询 fetcher。
OpenRouter 为 OpenAI 兼容聚合网关，协议走系统 openai-family，无需自定义 model_adapter。
"""

from typing import Any, Dict, Optional

from app.plugins.registries.provider_registry import ProviderDef


def _fetch_openrouter_balance(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """OpenRouter 余额查询：GET /api/v1/credits，余额 = total_credits - total_usage（美元）。"""
    import requests

    api_key = (config.get("API_KEY", "") or "").strip()
    if not api_key:
        return None
    try:
        resp = requests.get(
            "https://openrouter.ai/api/v1/credits",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
    except Exception:
        return {"hide": True}
    if resp.status_code != 200:
        return {"hide": True, "tooltip": f"余额查询失败 (HTTP {resp.status_code})"}
    try:
        data = (resp.json() or {}).get("data", {}) or {}
        total_credits = float(data.get("total_credits") or 0)
        total_usage = float(data.get("total_usage") or 0)
    except Exception:
        return {"hide": True, "tooltip": "余额查询异常: 响应不是 JSON"}
    return {"balance": round(total_credits - total_usage, 2), "currency": "$"}


# 聚合网关能力取各旗舰模型的公共交集（vision/thinking 主流模型均支持）
_OPENROUTER_CAPABILITIES = {
    "context_limit": 200000,
    "max_output_tokens": 16384,
    "absolute_limit": 65536,
    "supports_vision": True,
    "supports_thinking": True,
    "thinking_param": "reasoning_effort",
    "reasoning_effort_param": "reasoning_effort",
}


def register(registry):
    """注册 OpenRouter 服务商定义"""
    registry.register(
        ProviderDef(
            name="OpenRouter",
            icon="openrouter",
            api_url="https://openrouter.ai/api/v1",
            auth_type="bearer",
            default_model="anthropic/claude-sonnet-4.5",
            default_params={
                "温度": 0.7,
                "最大Token": 200000,
            },
            register_url="https://openrouter.ai/keys",
            models=[
                "anthropic/claude-opus-4.1",
                "anthropic/claude-sonnet-4.5",
                "anthropic/claude-haiku-4.5",
                "openai/gpt-5.1",
                "openai/gpt-5",
                "openai/gpt-4.1",
                "google/gemini-2.5-pro",
                "google/gemini-2.5-flash",
                "deepseek/deepseek-chat-v3.1",
                "x-ai/grok-4",
                "qwen/qwen3-235b-a22b",
                "moonshotai/kimi-k2",
                "meta-llama/llama-3.3-70b-instruct",
                "mistralai/mistral-large",
            ],
            models_dev_id="openrouter",
            family="openrouter",
            capabilities=_OPENROUTER_CAPABILITIES,
            balance_fetcher=_fetch_openrouter_balance,
        )
    )
