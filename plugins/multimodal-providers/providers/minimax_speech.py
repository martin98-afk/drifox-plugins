# -*- coding: utf-8 -*-
"""
服务商插件 — MiniMax 语音（合成 / 识别）

端点取插件库实证：
- 语音合成：`voice-reply` / `voice-clone` 走 api.minimaxi.com
  （/v1/audio/speech 为 OpenAI 兼容式，/v1/t2a_v2 为原生 T2A，两处共用同一 Key）
- 语音识别：`voice-input` 走 /v1/speech_to_text，multipart 上传 WAV + model 字段

与「海螺视频」同域但路径不同，config_id (URL, KEY) 不撞车。
"""

from app.plugins.registries.provider_registry import ProviderDef


def register(registry):
    """注册 MiniMax 语音能力服务商定义"""
    registry.register(
        ProviderDef(
            name="MiniMax 语音合成",
            icon="MiniMax",
            api_url="https://api.minimaxi.com/v1/audio/speech",
            auth_type="bearer",
            default_model="speech-2.6-hd",
            models=["speech-2.6-hd", "speech-2.8-hd"],
            capability_type="speech_generation",
            register_url="https://platform.minimaxi.com/user-center/basic-information/interface-key",
        )
    )

    registry.register(
        ProviderDef(
            name="MiniMax 语音识别",
            icon="MiniMax",
            api_url="https://api.minimaxi.com/v1/speech_to_text",
            auth_type="bearer",
            default_model="asr-1.0",
            models=["asr-1.0"],
            capability_type="speech_recognition",
            register_url="https://platform.minimaxi.com/user-center/basic-information/interface-key",
        )
    )
