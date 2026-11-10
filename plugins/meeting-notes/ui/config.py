# -*- coding: utf-8 -*-
"""插件配置读取。

两条硬约定（来自宿主能力契约）：
- 插件配置只能经 PluginConfigStore 读；不要去读 app.config（密钥是密文）。
- 「复用 voice-input 的 Key」是纯读取另一插件的公开配置项，不写对方任何东西。
"""

from __future__ import annotations

from typing import Any, Dict

from loguru import logger

PLUGIN_NAME = "meeting-notes"
VOICE_INPUT_PLUGIN = "voice-input"

SILICONFLOW_URL = "https://api.siliconflow.cn/v1/audio/transcriptions"
DEFAULT_MODEL = "XingChenAGI/XingChenASR-Diarize-V3.0"
DEFAULT_CHUNK_SEC = 20

# 支持说话人分离的模型（返回 segments[].speaker）
DIARIZE_MODELS = {
    "XingChenAGI/XingChenASR-Diarize-V3.0",
}

DEFAULTS: Dict[str, Any] = {
    "siliconflow_api_key": "",
    "reuse_voice_input_key": True,
    "asr_model": DEFAULT_MODEL,
    "chunk_seconds": DEFAULT_CHUNK_SEC,
    "keep_audio": True,
    "summary_model": "",
    "summary_prompt": "",
}


def _store():
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    return PluginConfigStore()


def read_config() -> Dict[str, Any]:
    """读取本插件配置；宿主不可用（单测/脚本）时返回默认值。"""
    cfg = dict(DEFAULTS)
    try:
        store = _store()
    except Exception as e:  # noqa: BLE001 — 配置系统不可用不阻塞录音
        logger.warning(f"[meeting-notes] 配置系统不可用，使用默认值: {e}")
        return cfg

    for key, default in DEFAULTS.items():
        try:
            value = store.get(PLUGIN_NAME, key)
        except Exception:  # noqa: BLE001
            value = None
        if value is None or value == "":
            value = default
        cfg[key] = value

    # 类型归一整：配置存储可能回字符串
    try:
        cfg["chunk_seconds"] = max(10, min(60, int(float(cfg.get("chunk_seconds") or DEFAULT_CHUNK_SEC))))
    except (TypeError, ValueError):
        cfg["chunk_seconds"] = DEFAULT_CHUNK_SEC
    cfg["reuse_voice_input_key"] = bool(cfg.get("reuse_voice_input_key"))
    cfg["keep_audio"] = bool(cfg.get("keep_audio"))
    return cfg


def resolve_api_key(cfg: Dict[str, Any]) -> str:
    """本插件 Key 优先；留空且允许复用时，读 voice-input 的硅基流动 Key。"""
    key = str(cfg.get("siliconflow_api_key") or "").strip()
    if key:
        return key
    if not cfg.get("reuse_voice_input_key", True):
        return ""
    try:
        borrowed = str(_store().get(VOICE_INPUT_PLUGIN, "siliconflow_api_key") or "").strip()
    except Exception as e:  # noqa: BLE001 — 对方插件没装/没配置属正常
        logger.debug(f"[meeting-notes] 复用 voice-input Key 失败: {e}")
        return ""
    if borrowed:
        logger.info("[meeting-notes] 使用 voice-input 插件的硅基流动 Key")
    return borrowed


def model_supports_diarize(model: str) -> bool:
    return model in DIARIZE_MODELS
