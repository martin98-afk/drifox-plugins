# -*- coding: utf-8 -*-
"""
服务商插件 — 火山引擎多模态能力（豆包语音合成 / 火山方舟图像 / 豆包录音识别）

原内置定义从 DriFox `plugins/system-providers/providers/volcengine.py` 迁出，
按能力类型拆成独立 ProviderDef：端点与 chat（api/coding/v3）不同域或不同路径，
规避 config_id (URL, KEY) 撞车。
"""

from app.plugins.registries.provider_registry import ProviderDef


def register(registry):
    """注册 火山引擎 多模态能力服务商定义"""

    # 语音合成：openspeech 域 v1 tts 端点，与 chat 端点不同域
    registry.register(
        ProviderDef(
            name="豆包语音合成",
            icon="火山引擎",
            api_url="https://openspeech.bytedance.com/api/v1/tts",
            auth_type="bearer",
            default_model="seed-tts-2.0-standard",
            models=["seed-tts-2.0-standard"],
            capability_type="speech_generation",
            register_url="https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey",
        )
    )

    # 图像生成：与 chat 同域但走通用 api/v3 端点，register_url 与 chat 同页
    registry.register(
        ProviderDef(
            name="火山方舟图像",
            icon="火山引擎",
            api_url="https://ark.cn-beijing.volces.com/api/v3",
            auth_type="bearer",
            default_model="doubao-seedream-4-0-250828",
            models=["doubao-seedream-4-0-250828"],
            capability_type="image_generation",
            register_url="https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey",
        )
    )

    # 语音识别：豆包家族 openspeech 域 v3 asr 端点
    registry.register(
        ProviderDef(
            name="豆包录音识别",
            icon="火山引擎",
            api_url="https://openspeech.bytedance.com/api/v3/asr",
            auth_type="bearer",
            default_model="seed-asr",
            models=["seed-asr"],
            capability_type="speech_recognition",
            register_url="https://console.volcengine.com/speech/app",
        )
    )
