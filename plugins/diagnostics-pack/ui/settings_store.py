# -*- coding: utf-8 -*-
"""诊断包选项：存在 ``<app_data>/plugin_data/diagnostics-pack/settings.json``。

不走宿主 config_schema，原因：
- 选项只有两个开关/数值，自绘卡已全部呈现，不需要 E1 自动卡兜底；
- 这样不依赖 ``plugin.config.write``（宿主较新才有的能力），旧宿主也能用。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

PLUGIN_NAME = "diagnostics-pack"

DEFAULTS: dict[str, Any] = {
    "include_crash_dumps": True,
    "max_mb": 50,
    "keep_runs": 5,
}


def _coerce(raw: dict[str, Any]) -> dict[str, Any]:
    values = dict(DEFAULTS)
    if not isinstance(raw, dict):
        return values
    if "include_crash_dumps" in raw:
        values["include_crash_dumps"] = bool(raw["include_crash_dumps"])
    for key in ("max_mb", "keep_runs"):
        try:
            values[key] = int(raw.get(key, values[key]))
        except (TypeError, ValueError):
            pass
    values["max_mb"] = max(5, min(1000, values["max_mb"]))
    values["keep_runs"] = max(1, min(50, values["keep_runs"]))
    return values


def settings_path(data_dir: Path) -> Path:
    return Path(data_dir) / "plugin_data" / PLUGIN_NAME / "settings.json"


def load_settings(data_dir: Path) -> dict[str, Any]:
    path = settings_path(data_dir)
    try:
        return _coerce(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_settings(data_dir: Path, values: dict[str, Any]) -> None:
    """原子写：先写临时文件再 replace，避免半截 JSON 卡住下次读取。"""
    path = settings_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(_coerce(values), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
