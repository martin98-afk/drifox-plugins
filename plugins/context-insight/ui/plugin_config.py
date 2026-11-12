# -*- coding: utf-8 -*-
"""插件配置与数据目录 —— 不依赖宿主主程序模块。

数据根目录由 UI ctx 的 ``storage.data_dir`` 能力注入；无 ctx 的场景
（hooks）按环境变量与常见安装位置发现。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

_PLUGIN = "context-insight"
_DATA_ROOT: Optional[Path] = None


def set_data_root(path: Any) -> None:
    global _DATA_ROOT
    try:
        candidate = Path(str(path))
    except Exception:
        return
    if candidate:
        _DATA_ROOT = candidate


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []
    env_dir = os.environ.get("DRIFOX_DATA_DIR")
    if env_dir:
        roots.append(Path(env_dir))
    roots.extend(
        [
            Path(".drifox"),
            Path.home() / ".drifox",
            Path.home() / "Library" / "Application Support" / "Drifox" / ".drifox",
        ]
    )
    return roots


def data_root() -> Path:
    global _DATA_ROOT
    if _DATA_ROOT is not None:
        return _DATA_ROOT
    for root in _candidate_roots():
        if (root / "plugins").exists() or (root / "plugin_data").exists():
            _DATA_ROOT = root
            return root
    _DATA_ROOT = Path.home() / ".drifox"
    return _DATA_ROOT


def plugin_data_dir() -> Path:
    return data_root() / "plugin_data" / _PLUGIN


def config_path() -> Path:
    return plugin_data_dir() / "config.json"


def read_config() -> Dict[str, Any]:
    path = config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def get_config(key: str, default: Any = None) -> Any:
    value = read_config().get(key)
    return default if value is None else value
