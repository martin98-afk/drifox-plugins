# -*- coding: utf-8 -*-
"""模型定价 —— 复用宿主 models.dev 缓存，缺失时回退内置常用价目表。

价格单位统一为 USD / 1M tokens。宿主缓存结构：
``<app_data>/cache/models_dev_cache.json`` → ``model_capabilities`` 或
``model_capabilities_partitioned``，每项含 ``cost.{input,output,cache_read,cache_write}``。
"""

from __future__ import annotations

import json
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from loguru import logger

_CACHE: Optional[Dict[str, Any]] = None
_CACHE_MTIME: float = 0.0
_TABLE_CACHE: Dict[str, Tuple[float, float]] = {}
_TABLE_MTIME: float = -1.0
# 归一化名 → 价格（表变化时整体重建）
_NORM_INDEX: Dict[str, Tuple[float, float]] = {}
_NORM_INDEX_KEY: str = ""
# 定价表文件探针节流：analyze 会成千上万次问价，不能每次都 stat 磁盘
_LAST_PROBE: float = 0.0
_PROBE_INTERVAL: float = 2.0
_CANDIDATES = (
    Path(".drifox") / "cache" / "models_dev_cache.json",
    Path.home() / ".drifox" / "cache" / "models_dev_cache.json",
    Path.home() / "Library" / "Application Support" / "Drifox" / ".drifox" / "cache" / "models_dev_cache.json",
)

# 内置兜底（USD / 1M）。仅在宿主缓存完全缺失时使用，标注为近似值。
_FALLBACK: Dict[str, Tuple[float, float]] = {
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
    "deepseek-v3": (0.27, 1.10),
    "deepseek-r1": (0.55, 2.19),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-opus-4": (15.00, 75.00),
    "qwen-plus": (0.40, 1.60),
    "qwen-max": (1.60, 6.40),
    "glm-4": (0.60, 2.20),
    "kimi-k2": (0.60, 2.50),
    "minimax-m2": (0.30, 1.20),
}


def _cache_paths() -> list[Path]:
    paths: list[Path] = []
    try:
        from .plugin_config import data_root

        paths.append(data_root() / "cache" / "models_dev_cache.json")
    except Exception:
        pass
    paths.extend(_CANDIDATES)
    return paths


def _load_cache() -> Dict[str, Any]:
    global _CACHE, _CACHE_MTIME, _LAST_PROBE
    if _CACHE is not None and time.monotonic() - _LAST_PROBE < _PROBE_INTERVAL:
        return _CACHE
    _LAST_PROBE = time.monotonic()
    for path in _cache_paths():
        if not path.exists():
            continue
        try:
            mtime = path.stat().st_mtime
            if _CACHE is not None and mtime == _CACHE_MTIME:
                return _CACHE
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _CACHE = data
                _CACHE_MTIME = mtime
                return data
        except Exception as e:
            logger.debug(f"[context-insight] 读定价缓存失败 {path}: {e}")
    _CACHE = {}
    return _CACHE


@lru_cache(maxsize=8192)
def _norm_model(name: str) -> str:
    text = (name or "").strip().lower()
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    text = re.sub(r":(free|beta|preview|latest)$", "", text)
    text = re.sub(r"[-_]?\d{4}-\d{2}-\d{2}$", "", text)
    return text


def _cost_of(entry: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    cost = entry.get("cost") if isinstance(entry, dict) else None
    if not isinstance(cost, dict):
        return None
    try:
        in_price = float(cost.get("input")) if cost.get("input") is not None else None
        out_price = float(cost.get("output")) if cost.get("output") is not None else None
    except (TypeError, ValueError):
        return None
    if in_price is None and out_price is None:
        return None
    return (in_price or 0.0, out_price or 0.0)


def _lookup_table() -> Dict[str, Tuple[float, float]]:
    global _TABLE_CACHE, _TABLE_MTIME
    data = _load_cache()
    if _TABLE_CACHE and _TABLE_MTIME == _CACHE_MTIME:
        return _TABLE_CACHE
    table: Dict[str, Tuple[float, float]] = {}
    flat = data.get("model_capabilities")
    if isinstance(flat, dict):
        for model_id, entry in flat.items():
            cost = _cost_of(entry)
            if cost is not None:
                table.setdefault(str(model_id), cost)
    partitioned = data.get("model_capabilities_partitioned")
    if isinstance(partitioned, dict):
        for _provider, models in partitioned.items():
            if not isinstance(models, dict):
                continue
            for model_id, entry in models.items():
                cost = _cost_of(entry)
                if cost is not None:
                    table.setdefault(str(model_id), cost)
    _TABLE_CACHE = table
    _TABLE_MTIME = _CACHE_MTIME
    return table


def _norm_index() -> Dict[str, Tuple[float, float]]:
    """归一化名 → 价格。同归一化名取最短原始 id，与旧版候选排序口径一致。"""
    global _NORM_INDEX, _NORM_INDEX_KEY
    table = _lookup_table()
    key = f"{_CACHE_MTIME}|{len(table)}"
    if _NORM_INDEX and _NORM_INDEX_KEY == key:
        return _NORM_INDEX
    index: Dict[str, Tuple[float, float]] = {}
    for mid, price in sorted(table.items(), key=lambda kv: len(kv[0])):
        index.setdefault(_norm_model(mid), price)
    _NORM_INDEX, _NORM_INDEX_KEY = index, key
    return index


@lru_cache(maxsize=4096)
def _price_cached(model: str, mtime: float) -> Tuple[float, float, bool]:
    index = _norm_index()
    norm = _norm_model(model)
    if norm:
        price = index.get(norm)
        if price is not None:
            return price[0], price[1], True
        # 前缀匹配：models.dev 的 id 常带日期与版本后缀
        for mid_norm, price in index.items():
            if mid_norm.startswith(norm + "-") or norm.startswith(mid_norm + "-"):
                return price[0], price[1], True

    for key, price in _FALLBACK.items():
        if key in norm or norm in key:
            return price[0], price[1], False
    return 0.0, 0.0, False


def price_for(model: str) -> Tuple[float, float, bool]:
    """返回 (input_price, output_price, known)，单位 USD / 1M tokens。"""
    _lookup_table()  # 同步 _CACHE_MTIME，表变则缓存键变
    return _price_cached(model or "", _CACHE_MTIME)


@lru_cache(maxsize=4096)
def _context_limit_cached(model: str, mtime: float) -> int:
    data = _CACHE or {}
    norm = _norm_model(model)
    for section in ("model_capabilities", "model_capabilities_partitioned"):
        block = data.get(section)
        if not isinstance(block, dict):
            continue
        if section == "model_capabilities":
            entry = block.get(norm)
            if isinstance(entry, dict):
                return int(entry.get("context_limit") or 0)
            for mid, item in block.items():
                if _norm_model(mid) == norm and isinstance(item, dict):
                    return int(item.get("context_limit") or 0)
        else:
            for models in block.values():
                if not isinstance(models, dict):
                    continue
                entry = models.get(norm)
                if isinstance(entry, dict):
                    return int(entry.get("context_limit") or 0)
    return 0


def context_limit_for(model: str) -> int:
    """模型上下文窗口（models.dev），未知返回 0。"""
    _load_cache()
    return _context_limit_cached(model or "", _CACHE_MTIME)
