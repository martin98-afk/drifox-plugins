# -*- coding: utf-8 -*-
"""see-now 配置读取（走宿主统一存储）。

配置由 plugin.json 的 `config_schema` 承载（E1 自动卡渲染在「设置 → 插件 → 看屏幕」），
本模块只负责读。`PluginConfigStore.get()` 有 schema 时会自动套默认值并把数字还原成
字符串，所以这里逐 key 取值再自行收敛成 int/bool。

**没有变更通知**：宿主的 PluginConfigStore / PluginConfigRegistry 都不发信号。
所以改完配置要靠 CaptureLoop 自己定期比对指纹（见 pipeline.py），不能指望回调。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from loguru import logger

PLUGIN_NAME = "see-now"


@dataclass(frozen=True)
class SeeNowConfig:
    enabled: bool = True
    fps: int = 1
    threshold: int = 12
    fallback_seconds: int = 20
    max_frames: int = 6


DEFAULTS = SeeNowConfig()

# key → (下限, 上限)
# fps 上限 6：实测单帧约 104ms，6fps 已经吃掉 62% 单核，再高不值。
FIELD_SPECS: dict[str, tuple[float, float]] = {
    "fps": (1, 6),
    "threshold": (0, 255),
    "fallback_seconds": (3, 300),
    "max_frames": (1, 6),
}


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    if text in ("true", "1", "yes", "on"):
        return True
    if text in ("false", "0", "no", "off"):
        return False
    return default


def _as_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def load_config() -> SeeNowConfig:
    try:
        from app.plugins.managers.plugin_config_store import PluginConfigStore

        store = PluginConfigStore()
        get: Callable[[str], Any] = lambda key: store.get(PLUGIN_NAME, key)  # noqa: E731
    except Exception as e:  # noqa: BLE001 - 宿主未就绪时用默认值，不炸
        logger.debug(f"[see-now] 读配置失败（用默认值）: {e}")
        get = lambda _key: None  # noqa: E731

    values = {}
    for key, (low, high) in FIELD_SPECS.items():
        values[key] = _as_int(get(key), getattr(DEFAULTS, key), int(low), int(high))
    return SeeNowConfig(enabled=_as_bool(get("enabled"), DEFAULTS.enabled), **values)
