# -*- coding: utf-8 -*-
"""宿主环境适配：解析数据目录、读宿主版本。

与 ``collect`` / ``pack`` 分开，是为了让核心打包逻辑保持零宿主依赖（可单测）。
本模块只在宿主进程内被 tools / ui 调用。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PLUGIN_NAME = "diagnostics-pack"


def resolve_data_dir(surface: str) -> Path:
    """应用数据目录：能力池 ``storage.data_dir`` → 环境变量/平台默认回退。"""
    try:
        from app.plugins.sdk import caps_for

        root = caps_for("storage.data_dir", plugin=PLUGIN_NAME, surface=surface)
        if root:
            return Path(str(root))
    except Exception:  # noqa: BLE001 — 能力池不可用时走回退，不阻塞导出
        pass

    env_dir = os.environ.get("DRIFOX_DATA_DIR")
    if env_dir:
        return Path(env_dir)
    if getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS"):
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "Drifox" / ".drifox"
        return Path.home() / ".drifox"
    return Path.cwd() / ".drifox"


def host_version() -> str:
    """宿主版本（包元数据）；拿不到写 unknown，不猜。"""
    from .collect import detect_app_version

    return detect_app_version()
