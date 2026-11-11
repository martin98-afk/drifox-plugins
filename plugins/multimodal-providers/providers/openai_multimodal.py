# -*- coding: utf-8 -*-
"""
服务商插件 — OpenAI 图像生成 / 语音合成

端点与模型取插件库实证：
- 图像：`gpt-image-2` 技能走 OPENAI_BASE_URL 默认 api.openai.com/v1，
  模型 gpt-image-2 / gpt-image-1 / dall-e-3（后者为兼容旧网关）
- 语音：`voice-reply` 走 /v1/audio/speech

与 chat 定义（api.openai.com/v1）路径不同，config_id (URL, KEY) 不撞车。
"""

from app.plugins.registries.provider_registry import ProviderDef

_REGISTER_URL = "https://platform.openai.com/api-keys"


def register(registry):
    """注册 OpenAI 多模态能力服务商定义"""
    registry.register(
        ProviderDef(
            name="OpenAI 图像生成",
            icon="大模型",
            api_url="https://api.openai.com/v1/images/generations",
            auth_type="bearer",
            default_model="gpt-image-2",
            models=["gpt-image-2", "gpt-image-1", "dall-e-3"],
            capability_type="image_generation",
            register_url=_REGISTER_URL,
        )
    )

    registry.register(
        ProviderDef(
            name="OpenAI 语音合成",
            icon="大模型",
            api_url="https://api.openai.com/v1/audio/speech",
            auth_type="bearer",
            default_model="gpt-4o-mini-tts",
            models=["gpt-4o-mini-tts", "tts-1", "tts-1-hd"],
            capability_type="speech_generation",
            register_url=_REGISTER_URL,
        )
    )
