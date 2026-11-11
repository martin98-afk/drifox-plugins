# -*- coding: utf-8 -*-
"""
服务商插件 — 智谱语音合成

端点与模型取插件库实证 + 官方文档：
- `voice-reply` 走 open.bigmodel.cn/api/paas/v4/audio/speech
- 模型 glm-tts（文档 POST /paas/v4/audio/speech，model 枚举仅 glm-tts）

与 chat 定义（open.bigmodel.cn/api/coding/paas/v4）路径不同，
config_id (URL, KEY) 不撞车。
"""

from app.plugins.registries.provider_registry import ProviderDef


def register(registry):
    """注册 智谱 语音合成服务商定义"""
    registry.register(
        ProviderDef(
            name="智谱语音合成",
            icon="智谱",
            api_url="https://open.bigmodel.cn/api/paas/v4/audio/speech",
            auth_type="bearer",
            default_model="glm-tts",
            models=["glm-tts"],
            capability_type="speech_generation",
            register_url="https://bigmodel.cn/usercenter/proj-mgmt/apikeys",
        )
    )
