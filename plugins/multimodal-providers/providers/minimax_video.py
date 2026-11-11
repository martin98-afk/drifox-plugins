# -*- coding: utf-8 -*-
"""
服务商插件 — MiniMax 视频生成（海螺视频 / Hailuo H3）

与 MiniMax chat 定义（api.minimax.chat）不同域（api.minimaxi.com），
config_id (URL, KEY) 不撞车。两代模型的端点分属 v1 / v2，各自独立声明。
"""

from app.plugins.registries.provider_registry import ProviderDef


def register(registry):
    """注册 海螺视频 系列服务商定义"""
    registry.register(
        ProviderDef(
            name="海螺视频",
            icon="MiniMax",
            api_url="https://api.minimaxi.com/v1",
            auth_type="bearer",
            default_model="video-01",
            models=["video-01"],
            capability_type="video_generation",
            register_url="https://platform.minimaxi.com",
        )
    )

    # H3 走 v2 异步任务端点（create 后轮询 query），初代 video-01 在 v1 同步式端点
    registry.register(
        ProviderDef(
            name="海螺视频 H3",
            icon="MiniMax",
            api_url="https://api.minimaxi.com/v2/video_generation",
            auth_type="bearer",
            default_model="MiniMax-H3",
            models=["MiniMax-H3"],
            capability_type="video_generation",
            register_url="https://platform.minimaxi.com/user-center/basic-information/interface-key",
        )
    )
