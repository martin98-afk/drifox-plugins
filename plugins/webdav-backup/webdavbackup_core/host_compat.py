# -*- coding: utf-8 -*-
"""主程序依赖收口层（自包含保证）

所有对 app.* 内部模块的 import 集中在本文件，且每一处都带插件内等价回退：
主程序重构/移除这些模块时，插件功能不失效，只是回退到内置实现。

回退矩阵：
- app.utils.utils.get_app_data_dir            → ~/.drifox（打包版标准位置）
- app.plugins.managers.PluginConfigStore      → 插件内等价实现（同路径同格式扁平 dict）
- app.utils.app_restart.restart_application   → 插件内自重启（拉起新进程 + 优雅退出）
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

PLUGIN_NAME = "webdav-backup"

# 主程序重启前需剥离的子进程环境键（与官方 app_restart 同名单）
_RENDER_ENV_KEYS = (
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "QT_OPENGL",
    "QT_ANGLE_PLATFORM",
    "QSG_RHI",
    "QSG_RHI_BACKEND",
)

_ONE_SHOT_ARG_PREFIXES = (
    "--configure-auto-start=",
    "--startup-error-file=",
)


# ============================================================
#  数据目录
# ============================================================


def get_app_data_dir() -> Path:
    try:
        from app.utils.utils import get_app_data_dir

        return Path(get_app_data_dir())
    except Exception:
        # 打包版标准位置；dev 场景主程序模块必然可用，不会走到这里
        return Path.home() / ".drifox"


# ============================================================
#  配置存储（E1 同路径同格式等价实现）
# ============================================================


class _FallbackConfigStore:
    """PluginConfigStore 的插件内等价实现。

    路径与格式与 E1 契约一致：<app_data>/plugin_data/<name>/config.json（扁平 dict）。
    主程序恢复可用后无需迁移——两者读写同一文件。
    """

    @staticmethod
    def _path(plugin_name: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", plugin_name)[:64] or "__invalid__"
        return get_app_data_dir() / "plugin_data" / safe / "config.json"

    def _read_raw(self, plugin_name: str) -> Dict[str, Any]:
        try:
            data = json.loads(self._path(plugin_name).read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def get(self, plugin_name: str, key: str) -> Any:
        return self._read_raw(plugin_name).get(key)

    def set_values(self, plugin_name: str, values: Dict[str, Any]) -> bool:
        raw = self._read_raw(plugin_name)
        for k, v in values.items():
            if v is None or v == "":
                raw.pop(k, None)
            else:
                raw[k] = v
        try:
            path = self._path(plugin_name)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
            return True
        except Exception:
            return False


def get_config_store():
    """优先主程序 E1 实现；不可用时回退插件内等价实现（同文件双向兼容）"""
    try:
        from app.plugins.managers.plugin_config_store import PluginConfigStore

        return PluginConfigStore()
    except Exception:
        return _FallbackConfigStore()


# ============================================================
#  重启（官方逻辑优先，插件内自包含实现兜底）
# ============================================================


def restart_app() -> tuple:
    """重启 DriFox。返回 (ok, error_message)。

    优先走主程序官方 app_restart（含单实例锁释放等内部细节）；
    主程序模块缺失/改名时走下方自包含实现，行为等价。
    """
    try:
        from app.utils.app_restart import restart_application

        if restart_application():
            return True, ""
        return False, "主程序重启入口返回失败"
    except Exception:
        pass

    # ── 自包含实现 ──
    args = [a for a in sys.argv[1:] if not a.startswith(_ONE_SHOT_ARG_PREFIXES)]
    if getattr(sys, "frozen", False):
        argv = [sys.executable, *args]
    else:
        argv0 = sys.argv[0] if sys.argv else ""
        entry = os.path.abspath(argv0) if argv0 else os.path.abspath("main.py")
        argv = [sys.executable, entry, *args]
    env = {k: v for k, v in os.environ.items() if k not in _RENDER_ENV_KEYS}
    try:
        kwargs: dict = {"cwd": os.getcwd(), "env": env, "shell": False}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(argv, **kwargs)
    except Exception as e:
        return False, str(e)

    try:
        # 释放单实例锁（主程序模块存在才有；缺失跳过，最坏新进程多试一次）
        try:
            from app.core.single_instance import release_current_lock

            release_current_lock()
        except Exception:
            pass
        _quit_current_gracefully()
    except Exception:
        os._exit(0)
    return True, ""


def _quit_current_gracefully() -> None:
    """优雅退出 + 5s 兜底强杀；PyQt5/PySide6 双绑定兼容"""
    from PyQt5.QtCore import QTimer

    QTimer.singleShot(5000, lambda: os._exit(0))
    try:
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
    except Exception:
        app = None
    if app is None:
        try:
            from PySide6.QtWidgets import QApplication  # type: ignore

            app = QApplication.instance()
        except Exception:
            app = None
    if app is None:
        os._exit(0)
    app.quit()
