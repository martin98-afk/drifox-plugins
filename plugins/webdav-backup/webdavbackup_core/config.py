# -*- coding: utf-8 -*-
"""配置与状态读写

配置：PluginConfigStore 三级链（env → 存储 → default），由主程序设置卡写入。
状态：plugin_data/webdav-backup/state.json，记录最近备份/恢复结果（调度器判据）。
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, Dict, Optional

PLUGIN_NAME = "webdav-backup"

# 备份范围白名单（config_schema inc_* 字段 → 数据目录顶层目录名）
INCLUDE_FIELDS = {
    "inc_sessions": "sessions",
    "inc_assistant_hub": "assistant_hub",
    "inc_plugin_data": "plugin_data",
    "inc_plugins": "plugins",
    "inc_skills": "skills",
    "inc_teams": "teams",
    "inc_workflows": "workflows",
    "inc_projects": "projects",
    "inc_archived": "archived",
    "inc_workspaces": "workspaces",
    "inc_screenshots": "screenshots",
    "inc_backups": "backups",
}

# 范围默认值（设置在 UI 卡勾选，schema 无此字段时的兑底；大体积/可再生目录默认关）
INCLUDE_DEFAULTS = {
    dirname: dirname not in ("plugins", "workspaces", "screenshots", "backups")
    for dirname in INCLUDE_FIELDS.values()
}

# 中文名（UI 摘要展示用）
INCLUDE_LABELS = {
    "sessions": "会话",
    "assistant_hub": "助手数据",
    "plugin_data": "插件配置",
    "plugins": "已装插件",
    "skills": "技能",
    "teams": "团队",
    "workflows": "工作流",
    "projects": "项目",
    "archived": "归档",
    "workspaces": "工作区",
    "screenshots": "截图",
    "backups": "本地备份",
}

_STATE_LOCK = threading.Lock()


def _plugin_data_dir() -> Path:
    from webdavbackup_core import host_compat

    return host_compat.get_app_data_dir() / "plugin_data" / PLUGIN_NAME


def get_app_data_root() -> Path:
    """DriFox 数据根目录（备份对象）"""
    from webdavbackup_core import host_compat

    return host_compat.get_app_data_dir()


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
    from webdavbackup_core import host_compat

    store = host_compat.get_config_store()

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
    # 范围白名单：inc_* 取值（schema 无此字段，UI 卡写入存储）→ 选中目录集合
    include_dirs = {
        dirname
        for field, dirname in INCLUDE_FIELDS.items()
        if _to_bool(store.get(PLUGIN_NAME, field), INCLUDE_DEFAULTS[dirname])
    }
    raw_extra = store.get(PLUGIN_NAME, "include_extra") or ""
    include_extra = [
        seg.strip().strip("/").replace("\\", "/")
        for seg in re.split(r"[\n,，]", str(raw_extra))
    ]
    include_extra = [ln for ln in include_extra if ln]
    # 外部绝对路径（数据目录之外的自定义备份目标），每行/逗号一个
    raw_paths = store.get(PLUGIN_NAME, "include_paths") or ""
    include_paths = [seg.strip() for seg in re.split(r"[\n,，]", str(raw_paths))]
    include_paths = [seg for seg in include_paths if seg]
    return {
        "server_url": g("server_url", schema_defaults["server_url"]).strip(),
        "username": g("username", "").strip(),
        "password": g("password", ""),
        "remote_dir": g("remote_dir", schema_defaults["remote_dir"]).strip().strip("/"),
        "auto_backup": _to_bool(store.get(PLUGIN_NAME, "auto_backup"), schema_defaults["auto_backup"]),
        "interval_hours": max(1, _to_int(store.get(PLUGIN_NAME, "interval_hours"), schema_defaults["interval_hours"])),
        "keep_versions": max(1, _to_int(store.get(PLUGIN_NAME, "keep_versions"), schema_defaults["keep_versions"])),
        "encryption_password": g("encryption_password", ""),
        "include_dirs": include_dirs,
        "include_extra": include_extra,
        "include_paths": include_paths,
    }


def describe_scope(cfg: Dict[str, Any], max_items: int = 3) -> str:
    """摘要用：范围中文描述，如「会话/助手数据/插件配置 等 6 类」"""
    labels = [INCLUDE_LABELS[d] for d in INCLUDE_FIELDS.values() if d in cfg.get("include_dirs", set())]
    extra_n = len(cfg.get("include_extra", []))
    if extra_n:
        labels.append(f"额外 {extra_n} 项")
    if not labels:
        return "空（未选任何内容）"
    head = "/".join(labels[:max_items])
    return head if len(labels) <= max_items else f"{head} 等 {len(labels)} 类"


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
