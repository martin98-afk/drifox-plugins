# -*- coding: utf-8 -*-
"""宿主服务商配置接入层（voice-input）。

设计口径：**宿主有配置就用宿主，没有就回退插件自存**。
- 插件配置项 `host_provider` 存主程序里语音识别实例的配置 ID（空 = 不用宿主）
- `resolve_override()` 经能力池 `model.config_for(query, capability_type="speech_recognition")`
  取该实例的明文 Key / 端点 / 模型名
- 失败一律返回 None，调用方沿用原有「硅基流动 / MiniMax 自存 Key」识别链，
  行为与改造前完全一致

宿主实例在识别链里排首位（用户显式选了它），自存 Key 继续排后面作后备。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

HOST_PROVIDER_KEY = "host_provider"
CAPABILITY_TYPE = "speech_recognition"


def host_options(plugin: str) -> List[Tuple[str, str]]:
    """列出宿主里 `capability_type=speech_recognition` 的服务商实例。"""
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
            out.append((config_id, f"语音识别 · {name}"))
        return out
    except Exception as e:  # noqa: BLE001 — 宿主不可用不影响配置卡渲染
        logger.debug(f"[voice-input] 列宿主语音识别服务商失败: {e}")
        return []


def resolve_override(plugin: str, query: str) -> Optional[Dict[str, str]]:
    """把宿主实例解析成识别链可用的端点/模型/Key。

    Returns:
        {"api_url", "api_key", "api_model", "name"}；失败返回 None。
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
        name = str(
            resolved.get("name")
            or resolved.get("provider_name")
            or resolved.get("display_name")
            or "宿主服务商"
        ).strip()
        return {"api_url": url, "api_key": key, "api_model": model, "name": name}
    except Exception as e:  # noqa: BLE001 — 解析失败走回退
        logger.warning(f"[voice-input] 宿主服务商解析失败，回退插件配置: {e}")
        return None
