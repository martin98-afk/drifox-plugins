# -*- coding: utf-8 -*-
"""模型协议适配器 — 按模型名把请求分流到对应传输通道（id="oaipro-router"）。

背景：OAIPro 中转站按「模型」硬性限定协议，同一个 API_URL 下三条通道并存
（全部实测确认）：

| 模型族 | 唯一可用端点 | 实测证据 |
|--------|--------------|----------|
| gpt-4o / gpt-4.1 / gpt-5.4-mini / gpt-6.x / o3 / chat-latest | `/v1/chat/completions` | 200 |
| gpt-5-pro / 5.2-pro / 5.4-pro / 5.5-pro / 5.3-codex | `/v1/responses` | 404「Use v1/responses」 |
| claude-* | `/v1/messages` | 走 chat/completions 报 403「不支持该接口」 |

作用域：只对 `api_url` 含 oaipro 域名的配置生效——同名模型在别的服务商
（如 Anthropic 官方）走的是它自己的通道，不得被本插件劫持。

匹配优先级高于系统 openai-family（1）。worker 裁决顺序是「旧键 > 协议入口 >
adapter」，所以用户手选协议时本适配器自动让位。
"""

from __future__ import annotations

from typing import Any, Dict

from app.plugins.contracts.model_adapter import ProtocolFlags

_ANTHROPIC_TRANSPORT = "anthropic_messages"

# 命中本适配器的分数（系统 openai-family 是 1）
_MATCH_SCORE = 50

# 本插件管辖的网关域名
_OAIPRO_HOSTS = ("oaipro.com",)

# 只能走 responses 的模型（chat/completions 会 404 提示改端点）
_RESPONSES_ONLY_PREFIXES = (
    "gpt-5-pro",
    "gpt-5.1-pro",
    "gpt-5.2-pro",
    "gpt-5.3-pro",
    "gpt-5.4-pro",
    "gpt-5.5-pro",
    "gpt-5-codex",
    "gpt-5.3-codex",
    "o3-pro",
)

# 只能走 anthropic messages 的模型前缀
_ANTHROPIC_PREFIXES = ("claude-",)


def _model_name(llm_config: Dict[str, Any]) -> str:
    return str((llm_config or {}).get("模型名称", "") or "").strip().lower()


def _is_oaipro(llm_config: Dict[str, Any]) -> bool:
    api_url = str((llm_config or {}).get("API_URL", "") or "").lower()
    return any(host in api_url for host in _OAIPRO_HOSTS)


def _is_anthropic_model(model: str) -> bool:
    return model.startswith(_ANTHROPIC_PREFIXES)


def _is_responses_only(model: str) -> bool:
    return model.startswith(_RESPONSES_ONLY_PREFIXES)


class OAIProRouterAdapter:
    """OAIPro 模型族路由器（只决定走哪条通道，不改消息形态）。"""

    id = "oaipro-router"

    def matches(self, llm_config: Dict[str, Any]) -> int:
        """仅 OAIPro 网关下的 claude 系与 responses-only 变体命中。"""
        if not _is_oaipro(llm_config):
            return 0
        model = _model_name(llm_config)
        if not model:
            return 0
        if _is_anthropic_model(model) or _is_responses_only(model):
            return _MATCH_SCORE
        return 0

    def protocol_flags(self, llm_config: Dict[str, Any]) -> ProtocolFlags:
        model = _model_name(llm_config)
        if _is_anthropic_model(model):
            return ProtocolFlags(
                is_gemini=False,
                requires_reasoning_content=False,
                use_responses_api=False,
                serializer_id="openai",
                protocol="openai",
                # worker 从 flags.extra["transport"] 取 transport id
                extra={"transport": _ANTHROPIC_TRANSPORT},
            )
        # 仅 responses 的 gpt 变体：与系统 openai-family 的 responses 分支等价
        return ProtocolFlags(
            is_gemini=False,
            requires_reasoning_content=False,
            use_responses_api=True,
            serializer_id="openai",
            protocol="responses",
            extra={"transport": "openai_responses"},
        )


def register(registry):
    registry.register(OAIProRouterAdapter())
