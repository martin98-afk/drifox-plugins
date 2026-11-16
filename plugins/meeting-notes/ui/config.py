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
DEFAULT_CHUNK_SEC = 60
# 纪要生成超时（秒）。转写稿长、模型慢时可自行调大。
DEFAULT_SUMMARY_TIMEOUT_SEC = 180
SUMMARY_TIMEOUT_MIN = 60
SUMMARY_TIMEOUT_MAX = 600

# 支持说话人分离的模型（返回 segments[].speaker）
DIARIZE_MODELS = {
    "XingChenAGI/XingChenASR-Diarize-V3.0",
}

DEFAULTS: Dict[str, Any] = {
    "host_provider": "",
    "siliconflow_api_key": "",
    "reuse_voice_input_key": True,
    "asr_model": DEFAULT_MODEL,
    "chunk_seconds": DEFAULT_CHUNK_SEC,
    "summary_timeout_sec": DEFAULT_SUMMARY_TIMEOUT_SEC,
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
    try:
        cfg["summary_timeout_sec"] = max(
            SUMMARY_TIMEOUT_MIN,
            min(
                SUMMARY_TIMEOUT_MAX,
                int(float(cfg.get("summary_timeout_sec") or DEFAULT_SUMMARY_TIMEOUT_SEC)),
            ),
        )
    except (TypeError, ValueError):
        cfg["summary_timeout_sec"] = DEFAULT_SUMMARY_TIMEOUT_SEC

    # 宿主服务商：显式选中且解析成功时，端点/Key/模型三项以宿主为准
    host = resolve_host_provider(cfg)
    if host:
        cfg["asr_url"] = host["api_url"]
        cfg["asr_key"] = host["api_key"]
        if host["api_model"]:
            cfg["asr_model"] = host["api_model"]
    return cfg


def resolve_api_key(cfg: Dict[str, Any]) -> str:
    """宿主实例 Key 优先，其次本插件，最后复用 voice-input 的硅基流动 Key。"""
    host_key = str(cfg.get("asr_key") or "").strip()
    if host_key:
        return host_key
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

HOST_PROVIDER_KEY = "host_provider"
ASR_CAPABILITY = "speech_recognition"

def resolve_host_provider(cfg: Dict[str, Any]) -> Dict[str, str]:
    """宿主语音识别实例 → {api_url, api_key, api_model}；未选/失败返回空 dict。

    空 dict 即「回退」：调用方继续用内置硅基流动端点 + 自填/复用 Key，
    行为与接入前完全一致。
    """
    query = str(cfg.get(HOST_PROVIDER_KEY) or "").strip()
    if not query:
        return {}
    try:
        from app.plugins.sdk import pool_for

        pool = pool_for(plugin=PLUGIN_NAME, surface="ui")
        if pool is None or "model.config_for" not in pool:
            return {}
        resolved = pool["model.config_for"](query, capability_type=ASR_CAPABILITY)
        if not isinstance(resolved, dict):
            return {}
        # 旧宿主解析器不吃 capability_type 时会退回旧签名，可能解析出 chat 实例
        if str(resolved.get("capability_type") or "") != ASR_CAPABILITY:
            return {}
        url = str(resolved.get("API_URL") or "").strip()
        key = str(resolved.get("API_KEY") or "").strip()
        if not url or not key:
            return {}
        return {
            "api_url": url,
            "api_key": key,
            "api_model": str(resolved.get("模型名称") or "").strip(),
        }
    except Exception as e:  # noqa: BLE001 — 解析失败走回退
        logger.warning(f"[meeting-notes] 宿主服务商解析失败，回退插件配置: {e}")
        return {}

def asr_url(cfg: Dict[str, Any]) -> str:
    """识别端点：宿主实例优先，其次内置硅基流动端点。"""
    return str(cfg.get("asr_url") or "").strip() or SILICONFLOW_URL
