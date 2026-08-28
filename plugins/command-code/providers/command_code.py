# -*- coding: utf-8 -*-
"""
服务商插件 — Command Code

数据全部由本插件声明（万物为插件）：icon / API URL / 默认参数 / 模型列表 /
family 能力。
Command Code 为 OpenAI 兼容聚合网关（亦提供 Anthropic 兼容端点），协议走系统
openai-family，无需自定义 model_adapter。API key 以 Bearer token 传递。
模型库覆盖 Claude / GPT / Gemini / DeepSeek / Kimi / GLM / MiniMax 等主流与开源
模型，按量付费、无加价，deal 自动生效。
"""

from app.plugins.registries.provider_registry import ProviderDef


def register(registry):
    """注册 Command Code 服务商定义"""
    registry.register(
        ProviderDef(
            name="Command Code",
            icon="commandcode",
            api_url="https://api.commandcode.ai/provider/v1",
            auth_type="bearer",
            default_model="deepseek/deepseek-v4-flash",
            default_params={
                "温度": 0.7,
                "最大Token": 200000,
            },
            register_url="https://commandcode.ai/studio/provider",
            models=[
                "deepseek/deepseek-v4-flash",
                "deepseek/deepseek-v4-pro",
                "claude-sonnet-5",
                "gpt-5.5",
                "gpt-5.4",
                "gpt-5.3-codex",
                "moonshotai/Kimi-K2.5",
                "google/gemini-3.7-flash",
                "minimax-m3",
                "mimo-v2.5",
                "mimo-v2.5-pro",
            ],
            models_dev_id="commandcode",
            family="commandcode",
            capabilities={
                "context_limit": 200000,
                "max_output_tokens": 16384,
                "absolute_limit": 65536,
                "supports_vision": True,
                "supports_thinking": True,
                "thinking_param": None,
            },
        )
    )
