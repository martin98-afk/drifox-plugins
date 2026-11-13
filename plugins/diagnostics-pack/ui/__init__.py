# -*- coding: utf-8 -*-
"""diagnostics-pack UI：设置卡 + ``/diag`` 命令。

组件分工：
- 设置卡（自绘）：选项、立即导出、打开目录、结果回显
- 命令：命令行/快捷键路径，参数 ``--open`` 导出后打开目录
两者共用 ``export_runner``（QThread）与 ``settings_store``（选项）。
"""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

PLUGIN_NAME = "diagnostics-pack"
_PLUGIN_DIR = Path(__file__).resolve().parent.parent
_MODULE_PREFIX = "ui_plugin_diagnostics_pack."
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))


def _clear_stale_submodules() -> None:
    """热重载：清掉本插件旧子模块，避免用到上一版 config_card / runner。"""
    for name in [key for key in sys.modules if key.startswith(_MODULE_PREFIX)]:
        if name != __name__:
            sys.modules.pop(name, None)


def _register_settings_card(registry) -> None:
    try:
        from .config_card import DiagnosticsCard

        registry.register_settings_card(
            PLUGIN_NAME,
            f"{PLUGIN_NAME}-settings",
            "诊断包",
            DiagnosticsCard,
            priority=1,
        )
    except Exception as exc:  # noqa: BLE001 — 旧宿主无该方法时不阻断命令入口
        logger.warning(f"[diagnostics-pack] 设置卡注册失败: {exc}")


def _register_command() -> None:
    try:
        from app.core.commands.builtin_commands import FunctionCommandHandlers

        from .command_export import run

        FunctionCommandHandlers.register("diag", run)
    except Exception as exc:  # noqa: BLE001 — 宿主无该 API 时只剩设置卡入口
        logger.warning(f"[diagnostics-pack] /diag 命令注册失败: {exc}")


def register_ui(registry) -> None:
    """主程序加载 UI 组件时调用；热重载会重复调用，需保持幂等。"""
    _clear_stale_submodules()
    _register_settings_card(registry)
    _register_command()
    logger.info("[diagnostics-pack] UI 已注册：设置卡 + /diag")
