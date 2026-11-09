# -*- coding: utf-8 -*-
"""gateway-dingtalk UI 组件入口 — 注册扫码登录设置卡。

点「扫码登录」→ 弹窗展示二维码 → 后台轮询设备注册状态 → 确认后写凭据并重连网关。

注册失败（qfluentwidgets 缺失 / 老宿主无 register_settings_card）时降级到
config_schema 自动卡（client_id/client_secret 可手填），插件不会因此变砖。

⚠️ UI 改动不热重载，改本目录后须重启宿主。
"""

import sys

from loguru import logger

PLUGIN_NAME = "gateway-dingtalk"


def register_ui(registry) -> None:
    """注册设置卡（热重载兼容：清理子模块缓存）"""
    prefix = "ui_plugin_gateway_dingtalk."
    for key in [k for k in sys.modules if k.startswith(prefix)]:
        del sys.modules[key]

    try:
        from .config_card import DingtalkConfigCard

        registry.register_settings_card(
            PLUGIN_NAME,
            f"{PLUGIN_NAME}-config",
            "钉钉机器人配置",
            DingtalkConfigCard,
            priority=1,
        )
        logger.info("[gateway-dingtalk] 设置卡已注册")
    except Exception as e:  # noqa: BLE001 — 降级 E1 自动卡
        logger.warning(f"[gateway-dingtalk] 设置卡注册失败（降级 E1 自动卡）: {e}")


def unload_ui(registry) -> None:
    """卸载钩子（无残留状态需清理）"""
