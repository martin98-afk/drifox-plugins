# -*- coding: utf-8 -*-
"""
服务商插件 — Tencent Hunyuan (TokenHub)

数据全部由本插件声明：icon / API URL / 默认参数 / 模型列表 /
models.dev 映射 / family 能力。
腾讯混元 Hy 系列经腾讯云 TokenHub 开放，OpenAI 兼容协议
（/v1/chat/completions），Bearer 鉴权，无需自定义 model_adapter。
协议走系统 openai-family（通用兜底适配器），Hy4 preview 当前在
WorkBuddy/CodeBuddy 限免两周（约 2026-09-11 止），Hy3 免费延至 2026-09-30。
"""

from typing import Any, Dict, Optional

from app.plugins.registries.provider_registry import ProviderDef


# TokenHub 为 OpenAI 兼容网关，能力取 Hy 系列公共交集
_TENCENT_HUNYUAN_CAPABILITIES = {
    "context_limit": 1000000,
    "max_output_tokens": 8192,
    "absolute_limit": 65536,
    "supports_vision": False,
    "supports_thinking": True,
    "thinking_param": "thinking",
}


def register(registry):
    """注册 Tencent Hunyuan (TokenHub) 服务商定义"""
    registry.register(
        ProviderDef(
            name="Tencent Hunyuan",
            icon="tencenthunyuan",
            api_url="https://tokenhub.tencentmaas.com/v1",
            auth_type="bearer",
            default_model="hy4-preview",
            default_params={
                "温度": 0.7,
                "最大Token": 1000000,
            },
            register_url="https://console.cloud.tencent.com/tokenhub/apikey",
            models=[
                "hy4-preview",
                "hy3",
            ],
            models_dev_id="tencent-hunyuan",
            family="tencent-hunyuan",
            capabilities=_TENCENT_HUNYUAN_CAPABILITIES,
        )
    )
