# -*- coding: utf-8 -*-
"""vision-proxy UI 组件入口 — 注册「图片代理（视觉模型）」设置卡。

本插件主体是 tools 组件（vision_describe），UI 只负责一张设置卡：
让用户在服务商 / 模型两级下拉里挑视觉模型，而不是手填名字。

注册失败（qfluentwidgets 缺失 / 能力不可用）时降级到 config_schema 自动卡
（text 字段手填），插件不会因此变砖。

⚠️ UI 改动不热重载，改本目录后须重启宿主。
"""

import sys

from loguru import logger


def register_ui(registry):
    """注册 vision-proxy 的设置卡。

    热重载兼容：清理 sys.modules 中残留的子模块缓存。
    """
    prefix = "ui_plugin_vision_proxy."
    for key in [k for k in sys.modules if k.startswith(prefix)]:
        del sys.modules[key]

    _register_config_card(registry)
    logger.info("[vision-proxy] UI components registered")


def _register_config_card(registry):
    """注册设置卡（失败降级 E1 自动卡）。"""
    try:
        from .config_card import _VisionConfigCard

        registry.register_settings_card(
            "vision-proxy",
            "vision-proxy-config",
            "图片代理（视觉模型）",
            _VisionConfigCard,
            priority=1,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[vision-proxy] 设置卡注册失败（降级 E1 自动卡）: {e}")


def unload_ui(registry):
    """卸载钩子（当前无残留状态需要清理）"""
