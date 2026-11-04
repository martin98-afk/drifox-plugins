# -*- coding: utf-8 -*-
"""speak-up 配置读取 — 走宿主统一存储（<app_data>/plugin_data/speak-up/config.json）。

**不声明 config_schema**：配置项太多，塞进「设置 → 插件」的卡片流里会挤成一长条。
改由插件自己的设置大 tab（register_settings_tab）承载完整表单。

没有 config_schema 时 `PluginConfigStore.get_all()` 返回空 dict（它按 schema 枚举字段），
所以这里逐个 key 调用 `get()`——它对无 schema 的插件直接返回文件里的原值。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from loguru import logger

PLUGIN_NAME = "speak-up"


@dataclass(frozen=True)
class SpeakUpConfig:
    """一次读取的配置快照（不可变，供定时线程安全使用）。"""

    enabled: bool = True
    dry_run: bool = True
    interval_minutes: int = 30
    peak_hit: int = 20
    valley_hit: int = 60
    miss_bonus: int = 10
    bonus_cap: int = 40
    near_minutes: int = 20
    near_factor_pct: int = 15
    far_minutes: int = 360
    far_factor_pct: int = 150
    cooldown_minutes: int = 20
    quiet_start_hour: int = 1
    quiet_end_hour: int = 8
    trigger_text: str = "好久没人跟我说话了，我该主动去打个招呼"

    @property
    def near_factor(self) -> float:
        return self.near_factor_pct / 100.0

    @property
    def far_factor(self) -> float:
        return self.far_factor_pct / 100.0


# 字段默认值（设置页与读取共用同一份，避免两处漂移）
DEFAULTS = SpeakUpConfig()

# key → (类型, 下限, 上限)
FIELD_SPECS: dict[str, tuple[str, float, float]] = {
    "interval_minutes": ("int", 1, 1440),
    "peak_hit": ("int", 0, 100),
    "valley_hit": ("int", 0, 100),
    "miss_bonus": ("int", 0, 100),
    "bonus_cap": ("int", 0, 100),
    "near_minutes": ("int", 0, 10080),
    "near_factor_pct": ("int", 0, 1000),
    "far_minutes": ("int", 0, 10080),
    "far_factor_pct": ("int", 0, 1000),
    "cooldown_minutes": ("int", 0, 1440),
    "quiet_start_hour": ("int", 0, 23),
    "quiet_end_hour": ("int", 0, 23),
}


def _store() -> Any:
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    return PluginConfigStore()


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


def load_config() -> SpeakUpConfig:
    """读一次配置。任何字段非法都回默认，不抛异常。"""
    try:
        store = _store()
        get: Callable[[str], Any] = lambda key: store.get(PLUGIN_NAME, key)  # noqa: E731
    except Exception as e:  # noqa: BLE001 - 宿主未就绪时用全默认，不炸
        logger.debug(f"[speak-up] 读配置失败（用默认值）: {e}")
        get = lambda _key: None  # noqa: E731

    values: dict[str, Any] = {}
    for key, (kind, low, high) in FIELD_SPECS.items():
        if kind == "int":
            values[key] = _as_int(get(key), getattr(DEFAULTS, key), int(low), int(high))

    trigger_text = str(get("trigger_text") or "").strip() or DEFAULTS.trigger_text

    return SpeakUpConfig(
        enabled=_as_bool(get("enabled"), DEFAULTS.enabled),
        dry_run=_as_bool(get("dry_run"), DEFAULTS.dry_run),
        trigger_text=trigger_text,
        **values,
    )


def save_config(values: dict[str, Any]) -> bool:
    """合并写入。空串 / None = 清除该键（回退默认）。"""
    try:
        return bool(_store().set_values(PLUGIN_NAME, values))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[speak-up] 保存配置失败: {e}")
        return False


def reset_config() -> bool:
    """删存储文件，全部回默认。"""
    try:
        return bool(_store().reset(PLUGIN_NAME))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[speak-up] 重置配置失败: {e}")
        return False
