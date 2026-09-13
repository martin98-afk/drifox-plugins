# -*- coding: utf-8 -*-
"""git-panel LLM 配置辅助 — 提交描述生成的模型解析与调用材料

复用主程序模型配置（与 prompt-enhancer 同约定，用户已确认接受复用私有状态）：
- app.config 的 LLM.SavedProviders 扫描「服务商:模型名」选项
- PluginConfigStore 读取 commit_prompt / commit_model 配置
- _get_llm_config：override 优先，回退调用方当前会话模型
"""

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

PLUGIN_NAME = "git-panel"

DEFAULT_COMMIT_PROMPT = (
    "你是一名资深软件工程师。请根据暂存区的代码变更生成一条简洁专业的 Git 提交描述："
    "使用中文；第一行概括本次变更的目的与要点（格式可参考 feat/fix/docs/chore: 范围 - 摘要）；"
    "如有关键改动点可用短句补充；不要用 Markdown 代码块包裹、不要解释，只输出提交描述本身。"
)

# 主程序 LLM 配置路径（与 prompt-enhancer 同约定）
_DEFAULT_SYSTEM_CONFIG_PATHS = (
    os.path.join(os.path.expanduser("~"), ".drifox", "app.config"),
    os.path.abspath(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "..", "..", ".drifox", "app.config")),
)

_SYSTEM_CONFIG_CACHE: Dict[str, Any] = {"path": None, "mtime": 0.0, "data": None}


def _resolve_system_config_path() -> Optional[str]:
    for p in _DEFAULT_SYSTEM_CONFIG_PATHS:
        if p and os.path.exists(p):
            return p
    return None


def _load_system_config() -> Optional[Dict[str, Any]]:
    """读取并缓存主程序 app.config（按 mtime 失效）。"""
    cfg_path = _resolve_system_config_path()
    if not cfg_path:
        return None
    try:
        mtime = os.path.getmtime(cfg_path)
    except OSError:
        return None
    cache = _SYSTEM_CONFIG_CACHE
    if cache["path"] == cfg_path and cache["mtime"] == mtime and cache["data"] is not None:
        return cache["data"]
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    cache["path"] = cfg_path
    cache["mtime"] = mtime
    cache["data"] = data
    return data


def parse_provider_options() -> List[Tuple[str, str]]:
    """扫描主程序 LLM.SavedProviders → [(「服务商:模型名」显示与值)]"""
    data = _load_system_config()
    if data is None:
        return []
    saved = ((data.get("LLM") or {}).get("SavedProviders") or {})
    out: List[Tuple[str, str]] = []
    seen = set()
    for _cid, p in saved.items():
        if not isinstance(p, dict):
            continue
        provider_name = str(p.get("provider_name") or p.get("name") or "").strip()
        models = list(p.get("模型列表") or [])
        if not models and p.get("模型名称"):
            models = [p.get("模型名称")]
        for m in models:
            m = str(m).strip()
            if not provider_name or not m:
                continue
            display = f"{provider_name}:{m}"
            if display in seen:
                continue
            seen.add(display)
            out.append((display, display))
    out.sort(key=lambda item: item[0].lower())
    return out


def parse_model_value(value: str) -> Optional[Tuple[str, str]]:
    """解析「服务商:模型名」→ (provider, model)；空/非法/不存在 → None"""
    if not value or ":" not in value:
        return None
    provider, model = value.split(":", 1)
    provider, model = provider.strip(), model.strip()
    if not provider or not model:
        return None
    for display, _v in parse_provider_options():
        if display == f"{provider}:{model}":
            return provider, model
    return None


def _get_provider_config_by_name(provider_name: str) -> Optional[Dict[str, Any]]:
    data = _load_system_config()
    if data is None:
        return None
    saved = ((data.get("LLM") or {}).get("SavedProviders") or {})
    for _cid, p in saved.items():
        if isinstance(p, dict) and (p.get("provider_name") or p.get("name") or "") == provider_name:
            return p
    return None


def get_llm_config(main_widget, override_provider: str = None, override_model: str = None) -> Optional[Dict[str, Any]]:
    """取本次生成用的模型配置；override 优先，回退调用方当前会话模型；无 → None"""
    if override_provider and override_model:
        provider_cfg = _get_provider_config_by_name(override_provider)
        if provider_cfg:
            merged = dict(provider_cfg)
            merged["模型名称"] = override_model
            return merged
    valid = getattr(main_widget, "_valid_configs", None)
    if not isinstance(valid, dict):
        return None
    name = getattr(main_widget, "_current_provider_name", None) or "系统默认配置"
    return valid.get(name)


def resolve_model(model_raw: str, main_widget) -> Optional[Tuple[str, str]]:
    """commit_model 配置 → (provider, model)；空/失败回退当前会话模型"""
    parsed = parse_model_value(str(model_raw) if model_raw else "")
    if parsed is not None:
        return parsed
    valid = getattr(main_widget, "_valid_configs", None)
    if isinstance(valid, dict):
        cur_name = getattr(main_widget, "_current_provider_name", None) or "系统默认配置"
        cur_cfg = valid.get(cur_name) or {}
        provider = cur_cfg.get("provider_name") or cur_cfg.get("name") or cur_name
        model = cur_cfg.get("模型名称") or ""
        if provider and model:
            return str(provider), str(model)
    return None


def strip_thinking(text: str) -> str:
    """移除模型输出中的 <think>…</think> 思考内容"""
    if not text:
        return text
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.strip()


def load_plugin_text_config(key: str, default: str) -> str:
    """读插件文本配置，空值回默认"""
    try:
        from app.plugins.managers.plugin_config_store import PluginConfigStore

        val = PluginConfigStore().get(PLUGIN_NAME, key)
    except Exception as e:
        logger.debug(f"[git-panel] 读配置 {key} 失败: {e}")
        val = None
    text = str(val).strip() if val else ""
    return text or default
