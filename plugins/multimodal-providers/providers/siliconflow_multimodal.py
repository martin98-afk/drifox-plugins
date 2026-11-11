# -*- coding: utf-8 -*-
"""
服务商插件 — 硅基流动语音（合成 / 识别）

端点与模型取插件库实证：
- 语音合成：`voice-reply` 走 /v1/audio/speech，预置 CosyVoice2-0.5B /
  fish-speech-1.5 / MOSS-TTSD-v0.5（音色包按模型区分）
- 语音识别：`voice-input` / `meeting-notes` 走 /v1/audio/transcriptions，
  预置 Qwen3-ASR 与 XingChenASR 系列（说话人分离需 Diarize 版）

与 chat 定义（api.siliconflow.cn/v1）路径不同，config_id (URL, KEY) 不撞车。
"""

from app.plugins.registries.provider_registry import ProviderDef

_REGISTER_URL = "https://cloud.siliconflow.cn/account/ak"


def register(registry):
    """注册 硅基流动 语音能力服务商定义"""
    registry.register(
        ProviderDef(
            name="硅基流动语音合成",
            icon="siliconflow",
            api_url="https://api.siliconflow.cn/v1/audio/speech",
            auth_type="bearer",
            default_model="FunAudioLLM/CosyVoice2-0.5B",
            models=[
                "FunAudioLLM/CosyVoice2-0.5B",
                "fishaudio/fish-speech-1.5",
                "fnlp/MOSS-TTSD-v0.5",
            ],
            capability_type="speech_generation",
            register_url=_REGISTER_URL,
        )
    )

    registry.register(
        ProviderDef(
            name="硅基流动语音识别",
            icon="siliconflow",
            api_url="https://api.siliconflow.cn/v1/audio/transcriptions",
            auth_type="bearer",
            default_model="Qwen/Qwen3-ASR-1.7B",
            models=[
                "Qwen/Qwen3-ASR-1.7B",
                "FunAudioLLM/SenseVoiceSmall",
                "XingChenAGI/XingChenASR-V3.2",
                "XingChenAGI/XingChenASR-V3.2-Ultra",
                "XingChenAGI/XingChenASR-Diarize-V3.0",
            ],
            capability_type="speech_recognition",
            register_url=_REGISTER_URL,
        )
    )
