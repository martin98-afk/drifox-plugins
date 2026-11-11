# -*- coding: utf-8 -*-
"""宿主服务商配置接入层（voice-reply）。

设计口径：**宿主有配置就用宿主，没有就回退插件自存**。
- 插件配置项 `host_provider` 存主程序里的服务商实例 id（空 = 不用宿主）
- `resolve_override()` 经能力池 `model.config_for(query, capability_type=...)`
  拿到该实例的明文 Key / 完整端点 / 模型名
- 任何一步失败（能力未授权、宿主未提供、解析不到、旧宿主忽略 capability_type
  解析成 chat 实例）一律返回 None，调用方沿用插件自存配置，行为与改造前一致

为什么独立成模块：能力池取值要能脱离 Qt 单测，也避免 ui/__init__.py 与
config_card.py 各写一份解析逻辑。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

# 插件配置键：选中的宿主服务商实例 id（空串表示走插件自存配置）
HOST_PROVIDER_KEY = "host_provider"
# 本插件消费的能力类型
CAPABILITY_TYPE = "speech_generation"


def host_options(plugin: str) -> List[Tuple[str, str]]:
    """列出宿主里能力类型匹配的服务商实例：[(config_id, 展示文案)]。

    只读 provider.list（不含密钥与 URL）。宿主不支持/未授权时返回空列表，
    配置卡据此只显示「插件内手填」一项。
    """
    try:
        from app.plugins.sdk import pool_for

        pool = pool_for(plugin=plugin, surface="ui")
        if pool is None or "provider.list" not in pool:
            return []
        out: List[Tuple[str, str]] = []
        for item in pool["provider.list"]() or []:
            if str(item.get("capability_type") or "") != CAPABILITY_TYPE:
                continue
            config_id = str(item.get("id") or "").strip()
            if not config_id:
                continue
            name = str(item.get("display_name") or item.get("provider_name") or config_id)
            out.append((config_id, f"语音合成 · {name}"))
        return out
    except Exception as e:  # noqa: BLE001 — 宿主不可用不应影响配置卡渲染
        logger.debug(f"[voice-reply] 列宿主语音服务商失败: {e}")
        return []


def resolve_override(plugin: str, query: str, current_voice: str = "") -> Optional[Dict[str, str]]:
    """解析宿主服务商实例为插件可直接使用的配置。

    Args:
        plugin: 插件名（能力池按它做授权裁剪）
        query: 服务商实例 id，形如 `abc123` 或 `abc123:模型名`
        current_voice: 插件当前音色值（`模型:音色`），用于把音色前缀换成宿主模型

    Returns:
        {"api_url", "api_key", "api_model"[, "api_voice"]}；失败返回 None。
        只覆盖这四项——音色与引擎开关仍归插件管。
    """
    query = str(query or "").strip()
    if not query:
        return None
    try:
        from app.plugins.sdk import pool_for

        pool = pool_for(plugin=plugin, surface="ui")
        if pool is None or "model.config_for" not in pool:
            return None
        resolved: Any = pool["model.config_for"](query, capability_type=CAPABILITY_TYPE)
        if not isinstance(resolved, dict):
            return None
        # 旧宿主解析器不吃 capability_type 时会退回旧签名，可能解析出 chat 实例
        if str(resolved.get("capability_type") or "") != CAPABILITY_TYPE:
            return None
        url = str(resolved.get("API_URL") or "").strip()
        key = str(resolved.get("API_KEY") or "").strip()
        model = str(resolved.get("模型名称") or "").strip()
        if not url or not key:
            return None
        out: Dict[str, str] = {"api_url": url, "api_key": key}
        if model:
            out["api_model"] = model
            voice_name = _split_voice(current_voice)
            if voice_name:
                # SiliconFlow 等网关的 voice 是「模型:音色」，前缀不跟着换会报音色不存在
                out["api_voice"] = f"{model}:{voice_name}"
        return out
    except Exception as e:  # noqa: BLE001 — 解析失败走回退
        logger.warning(f"[voice-reply] 宿主服务商解析失败，回退插件配置: {e}")
        return None


def _split_voice(value: str) -> str:
    """取音色短名：`模型:音色` → 音色；无冒号原样返回。"""
    text = str(value or "").strip()
    if not text:
        return ""
    if ":" in text:
        return text.split(":", 1)[1].strip()
    return text
