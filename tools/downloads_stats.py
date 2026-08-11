#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
downloads_stats.py — 插件下载量统计的公共工具模块（市场端）

统计链路（方案 A：客户端上报 + 计数服务 + CI 回写）：
    1. 客户端安装/更新插件成功后，GET {COUNT_API_BASE}/hit/{key} 计数 +1
    2. 本仓库 CI 定时跑 tools/fetch_downloads.py，从计数服务拉取各插件计数
    3. tools/generate_marketplace.py 把计数写入 marketplace.json 的 downloads 字段
    4. 客户端 UI 展示 downloads

计数服务选型说明：
    经典 countapi.xyz 已不稳定（2026 年起 SSL 握手失败），改用其开源替代
    CountAPI（https://countapi.mileshilliard.com，免注册、无鉴权、API 兼容）。
    如需切换服务，只需改 COUNT_API_BASE 与插件 key 生成规则，两侧（客户端
    上报 / 市场端拉取）保持一致的 key 命名即可。
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

# ============================================================
# 计数服务配置
# ============================================================

# 计数服务 API 根地址（get/hit 都基于它）
COUNT_API_BASE = "https://countapi.mileshilliard.com/api/v1"
# 统计 key 前缀：key = 前缀 + 插件名（服务不支持 namespace/key 两级路径）
COUNT_KEY_PREFIX = "drifox-plugins-"
# 请求 UA：不带 UA 会被服务 403 拒绝
_UA = "DriFox/0.5 (+https://github.com/martin98-afk/drifox-plugins)"


def plugin_counter_key(plugin_name: str) -> str:
    """生成插件对应的计数服务 key"""
    return f"{COUNT_KEY_PREFIX}{plugin_name}"


def _request(path: str, timeout: float = 8.0) -> Optional[Dict[str, Any]]:
    """GET 计数服务路径，返回 JSON dict；网络/解析失败返回 None"""
    req = urllib.request.Request(
        f"{COUNT_API_BASE}{path}",
        headers={"User-Agent": _UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def report_install(plugin_name: str) -> bool:
    """客户端安装/更新成功后调用：计数 +1（尽力而为，失败返回 False）

    Args:
        plugin_name: 插件名（marketplace.json 中的 name）

    Returns:
        True 上报成功
    """
    data = _request(f"/hit/{plugin_counter_key(plugin_name)}")
    return isinstance(data, dict) and "value" in data


def fetch_downloads(
    plugin_names: List[str],
    previous: Optional[Dict[str, int]] = None,
) -> Dict[str, int]:
    """从计数服务拉取各插件当前下载量（只读，不 +1）

    Args:
        plugin_names: 插件名列表
        previous: 上次缓存值（{name: count}），拉取失败时兜底保留旧值

    Returns:
        {插件名: 下载量}；拉取失败且无旧值的插件记 0
    """
    previous = previous or {}
    result: Dict[str, int] = {}
    for name in plugin_names:
        data = _request(f"/get/{plugin_counter_key(name)}")
        if isinstance(data, dict) and isinstance(data.get("value"), (int, float)):
            result[name] = int(data["value"])
        else:
            result[name] = previous.get(name, 0)
    return result


# ============================================================
# 本地缓存（downloads_cache.json）读写
# ============================================================

CACHE_SCHEMA_VERSION = 1


def load_downloads_cache(path: Path) -> Dict[str, Any]:
    """读取下载量缓存，损坏/缺失返回空结构"""
    default: Dict[str, Any] = {"schema": CACHE_SCHEMA_VERSION, "fetched_at": 0.0, "downloads": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return default
        downloads = data.get("downloads", {})
        if not isinstance(downloads, dict):
            downloads = {}
        return {
            "schema": CACHE_SCHEMA_VERSION,
            "fetched_at": data.get("fetched_at", 0.0),
            "downloads": {k: int(v) for k, v in downloads.items() if isinstance(v, (int, float))},
        }
    except Exception:
        return default


def save_downloads_cache(path: Path, downloads: Dict[str, int], fetched_at: float) -> None:
    """写下载量缓存（原子写入，避免 CI 中断产生半截文件）"""
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(
            {"schema": CACHE_SCHEMA_VERSION, "fetched_at": fetched_at, "downloads": downloads},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    tmp.replace(path)
