# -*- coding: utf-8 -*-
"""git-panel LLM 配置辅助 — 提交描述生成的模型解析与调用材料

复用主程序模型配置（与 prompt-enhancer 同约定），全部走宿主内存态：
- 服务商/模型两级下拉：provider.list / model.enumerate 能力（内存态，
  用户刚加的服务商立即可见）；能力不可用（旧宿主 / 无活跃窗口）下拉为空，
  已存配置由设置卡回显逻辑保留不丢。
- 明文 API_KEY 经宿主 services["get_provider_config"] 或能力池 model.config
  获取（内存态已解锁明文）；绝不 json.load(app.config)——密钥模式下磁盘
  API_KEY 是密文/空串，不可用于请求。
- PluginConfigStore 读取 commit_prompt / commit_provider / commit_model 配置
  （服务商、模型分开存，对齐 vision-proxy）；commit_model 存旧格式
  「服务商:模型名」合并值时按兼容路径拆分。
- get_llm_config：override 优先，回退调用方当前会话模型
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

PLUGIN_NAME = "git-panel"

DEFAULT_COMMIT_PROMPT = (
    "你是一名资深软件工程师。请根据暂存区的代码变更生成一条简洁专业的 Git 提交描述："
    "使用中文；第一行概括本次变更的目的与要点（格式可参考 feat/fix/docs/chore: 范围 - 摘要）；"
    "如有关键改动点可用短句补充；不要用 Markdown 代码块包裹、不要解释，只输出提交描述本身。"
)

def _caps(name: str) -> Any:
    """取宿主能力（设置卡无 ctx，走 caps_for 按插件名解析到活跃窗口）。"""
    try:
        from app.plugins.sdk import caps_for

        return caps_for(name, plugin=PLUGIN_NAME, surface="ui")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[git-panel] 取能力 {name} 失败: {e}")
        return None


def load_provider_entries() -> List[Dict[str, Any]]:
    """内存态服务商清单（provider.list 能力）；不可用返回 []（下拉留空保已存值）。"""
    fn = _caps("provider.list")
    if not callable(fn):
        return []
    try:
        items = fn() or []
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[git-panel] provider.list 调用失败: {e}")
        return []
    return [p for p in items if isinstance(p, dict)]


def load_models_of(provider_id: str) -> List[str]:
    """指定服务商的模型名列表（model.enumerate 能力）；不可用返回 []。"""
    if not provider_id:
        return []
    fn = _caps("model.enumerate")
    if not callable(fn):
        return []
    try:
        items = fn(provider_id) or []
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[git-panel] model.enumerate 调用失败: {e}")
        return []
    return [str(m.get("name") or "") for m in items if isinstance(m, dict) and m.get("name")]


def load_provider_tree() -> List[Tuple[str, str]]:
    """服务商两级下拉的第一级选项：[(display, config_id)]。

    走 provider.list（内存态，用户刚加的服务商立即可见）；能力不可用
    （旧宿主 / 无活跃窗口）返回 []，由设置卡回显逻辑保住已存值。
    """
    out: List[Tuple[str, str]] = []
    for p in load_provider_entries():
        pid = str(p.get("id") or "")
        if not pid:
            continue
        label = str(p.get("display_name") or pid)
        if p.get("is_current"):
            label = f"{label}（当前）"
        out.append((label, pid))
    return out


def load_models_by_tree(provider_id: str) -> List[str]:
    """服务商两级下拉的第二级选项：模型名列表（model.enumerate 能力）。

    能力不可用返回 []，由设置卡回显逻辑保住已存值。
    """
    return load_models_of(provider_id)


def _pool_resolve_config():
    """能力池 model.config 解析器（含明文 key 完整配置）；不可用返回 None。

    pool.legacy("get_provider_config", "model.config")：旧服务键优先、
    能力主实现兜底；两者同签名（无参 = 当前会话模型，带参 = 五级匹配）。
    """
    try:
        from app.plugins.sdk import pool_for

        pool = pool_for(plugin=PLUGIN_NAME, surface="ui")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[git-panel] 取能力池失败: {e}")
        return None
    if pool is None:
        return None
    try:
        resolve = pool.legacy("get_provider_config", "model.config")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[git-panel] model.config 能力不可用: {e}")
        return None
    return resolve if callable(resolve) else None


def get_llm_config(
    override_provider: str = None,
    override_model: str = None,
    services: Dict[str, Any] = None,
) -> Optional[Dict[str, Any]]:
    """取本次生成用的模型配置；override 优先，回退调用方当前会话模型；无 → None。

    取配置的唯一正确通道是宿主内存态，两路按优先级：
    1. ctx["services"]["get_provider_config"]（窗口上下文注入）；
    2. 能力池 model.config（caps_for 解析到活跃窗口）。
    **绝不 json.load(app.config)**：密钥模式下磁盘 API_KEY 是密文或空串，
    拿它发请求必然 401。
    """
    provider = override_provider or ""
    model = override_model or ""

    if isinstance(services, dict) and callable(services.get("get_provider_config")):
        get_cfg = services["get_provider_config"]
    else:
        get_cfg = _pool_resolve_config()
    if not callable(get_cfg):
        return None
    try:
        cfg = get_cfg(provider, model)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[git-panel] 模型配置解析失败: {e}")
        cfg = None
    # 判据是「配置非空」：免鉴权服务商 API_KEY 本为空，
    # build_openai_client 会剥掉 Authorization 头；
    # 服务返回空（服务商不存在 / 宿主未就绪）→ None，
    # 显式指名的服务商失效时不静默串到别的服务商
    if isinstance(cfg, dict) and cfg:
        return cfg
    return None


def resolve_model(provider_raw: str, model_raw: str) -> Optional[Tuple[str, str]]:
    """commit_provider + commit_model 配置 → (provider, model)；两键均空 → None。

    两键均空 = None = 沿用调用方当前会话模型（get_llm_config 传空
    provider/model 即取当前会话配置，与旧的内存兜底语义一致）。新格式两键
    分开存（对齐 vision-proxy）；commit_model 存旧格式「服务商:模型名」合并值
    时直接拆分。只配 provider 不配 model = 用该服务商的默认模型。
    """
    provider = str(provider_raw or "").strip()
    model = str(model_raw or "").strip()
    if not provider and ":" in model:
        # 旧格式兼容：「Provider:Model」合并值
        provider, model = model.split(":", 1)
        provider, model = provider.strip(), model.strip()
    if provider or model:
        return provider, model
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
