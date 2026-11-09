# -*- coding: utf-8 -*-
"""gateway-qq UI 组件入口 — 注册扫码绑定设置卡。

点「扫码登录」→ 弹窗展示二维码 → 后台轮询绑定状态 → 确认后解密回传凭据、
写配置并重连网关。

注册失败（qfluentwidgets 缺失 / 老宿主无 register_settings_card）时降级到
config_schema 自动卡（appid/app_secret 可手填），插件不会因此变砖。

⚠️ UI 改动不热重载，改本目录后须重启宿主。
"""

import sys

from loguru import logger

PLUGIN_NAME = "gateway-qq"


def register_ui(registry) -> None:
    """注册设置卡（热重载兼容：清理子模块缓存）"""
    prefix = "ui_plugin_gateway_qq."
    for key in [k for k in sys.modules if k.startswith(prefix)]:
        del sys.modules[key]

    try:
        from .config_card import QqConfigCard

        registry.register_settings_card(
            PLUGIN_NAME,
            f"{PLUGIN_NAME}-config",
            "QQ 机器人配置",
            QqConfigCard,
            priority=1,
        )
        logger.info("[gateway-qq] 设置卡已注册")
    except Exception as e:  # noqa: BLE001 — 降级 E1 自动卡
        logger.warning(f"[gateway-qq] 设置卡注册失败（降级 E1 自动卡）: {e}")


def unload_ui(registry) -> None:
    """卸载钩子（无残留状态需清理）"""
