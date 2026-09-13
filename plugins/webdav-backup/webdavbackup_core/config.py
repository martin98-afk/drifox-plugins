# -*- coding: utf-8 -*-
"""配置与状态读写

配置：PluginConfigStore 三级链（env → 存储 → default），由主程序设置卡写入。
状态：plugin_data/webdav-backup/state.json，记录最近备份/恢复结果（调度器判据）。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional

PLUGIN_NAME = "webdav-backup"

_STATE_LOCK = threading.Lock()


def _plugin_data_dir() -> Path:
    from app.utils.utils import get_app_data_dir

    return Path(get_app_data_dir()) / "plugin_data" / PLUGIN_NAME


def get_app_data_root() -> Path:
    """DriFox 数据根目录（备份对象）"""
    from app.utils.utils import get_app_data_dir

    return Path(get_app_data_dir())


def _to_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on", "是")
    if isinstance(v, (int, float)):
        return bool(v)
    return default


def _to_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def load_config() -> Dict[str, Any]:
    """读取插件配置（三级链兜底），字段已归一化"""
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    store = PluginConfigStore()

    def g(key: str, default: str = "") -> str:
        v = store.get(PLUGIN_NAME, key)
        if v is None or v == "":
            return default
        return str(v)

    schema_defaults = {
        "server_url": "https://dav.jianguoyun.com/dav/",
        "username": "",
        "password": "",
        "remote_dir": "drifox-backup",
        "auto_backup": True,
        "interval_hours": 24,
        "keep_versions": 10,
        "encryption_password": "",
    }
    return {
        "server_url": g("server_url", schema_defaults["server_url"]).strip(),
        "username": g("username", "").strip(),
        "password": g("password", ""),
        "remote_dir": g("remote_dir", schema_defaults["remote_dir"]).strip().strip("/"),
        "auto_backup": _to_bool(store.get(PLUGIN_NAME, "auto_backup"), schema_defaults["auto_backup"]),
        "interval_hours": max(1, _to_int(store.get(PLUGIN_NAME, "interval_hours"), schema_defaults["interval_hours"])),
        "keep_versions": max(1, _to_int(store.get(PLUGIN_NAME, "keep_versions"), schema_defaults["keep_versions"])),
        "encryption_password": g("encryption_password", ""),
    }


def is_configured(cfg: Optional[Dict[str, Any]] = None) -> bool:
    """服务器 + 账号 + 密码齐备才算已配置"""
    c = cfg or load_config()
    return bool(c.get("server_url") and c.get("username") and c.get("password"))


def load_state() -> Dict[str, Any]:
    path = _plugin_data_dir() / "state.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: Dict[str, Any]) -> None:
    with _STATE_LOCK:
        d = _plugin_data_dir()
        d.mkdir(parents=True, exist_ok=True)
        path = d / "state.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
