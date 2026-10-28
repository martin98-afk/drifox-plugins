# -*- coding: utf-8 -*-
"""gateway-wechat UI 组件入口 — 注册扫码登录设置卡。

本插件不再提供 tools 组件（wechat_login 已移除），扫码登录完全由本卡接管：
点「扫码登录」→ 弹窗展示二维码 → 后台长轮询 → 确认后写 bot_token 并重连网关。

注册失败（qfluentwidgets 缺失 / 老宿主无 register_settings_card）时降级到
config_schema 自动卡（bot_token 可手填），插件不会因此变砖。

⚠️ UI 改动不热重载，改本目录后须重启宿主。
"""

import sys

from loguru import logger

PLUGIN_NAME = "gateway-wechat"


def register_ui(registry) -> None:
    """注册设置卡（热重载兼容：清理子模块缓存）"""
    prefix = "ui_plugin_gateway_wechat."
    for key in [k for k in sys.modules if k.startswith(prefix)]:
        del sys.modules[key]

    try:
        from .config_card import WechatConfigCard

        registry.register_settings_card(
            PLUGIN_NAME,
            f"{PLUGIN_NAME}-config",
            "微信机器人配置",
            WechatConfigCard,
            priority=1,
        )
        logger.info("[gateway-wechat] 设置卡已注册")
    except Exception as e:  # noqa: BLE001 — 降级 E1 自动卡
        logger.warning(f"[gateway-wechat] 设置卡注册失败（降级 E1 自动卡）: {e}")


def unload_ui(registry) -> None:
    """卸载钩子（无残留状态需清理）"""
