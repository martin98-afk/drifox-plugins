# -*- coding: utf-8 -*-
"""vision_describe — 图片代理工具（vision-proxy 插件）。

用途：当前模型不支持视觉时，把图片转发给配置好的多模态模型，取回文字描述，
交给当前模型继续推理。

链路：
    1. 图片路径 / URL → data URI（本地文件 base64，远程 URL 原样透传）
    2. 宿主 get_provider_config(provider, model) 取含明文密钥的视觉模型配置
    3. 宿主 create_engine_session + model_config_override 发一轮多模态请求
    4. turn() 的文本作为工具结果回给当前模型

为什么走 engine.session 而不是自建 HTTP client：协议适配（chat/responses/
thinking 参数）、单向伪装头、max_tokens 钳制、智能重试全在引擎里，自建直发
会丢这些（实测非流式 400）。

为什么这两个能力要显式 surface="ui"：engine.session / model.config 的
provider 只注册在 ui surface（app/plugins/capabilities/providers/ui_core.py），
而工具插件的 tool_ctx["services"] 只投影 tool surface，拿不到。
"""

import base64
import os
import threading
from typing import Any, Dict, List, Tuple

from loguru import logger

from app.plugins.managers.plugin_config_store import PluginConfigStore
from app.plugins.sdk import ToolResult, pool_for

PLUGIN_NAME = "vision-proxy"
ENGINE_NAME = "vision-proxy"

# 单张图片上限（base64 前）。超过直接报错而不是静默降采样——降采样需要
# QImage（Qt 主线程亲和），工具线程里用有风险，宁可让用户自己压。
_MAX_BYTES = 8 * 1024 * 1024

_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

_DEFAULT_QUESTION = "请详细描述图片中的全部可见内容，包括文字、布局、主体对象与可辨识的细节。"

_SYSTEM_PROMPT = (
    "你是图片理解助手。只依据图片实际可见的内容作答，不猜测、不编造图片中不存在的"
    "信息；图片模糊或不完整时直接说明。用中文输出，不要复述问题。"
)


# ── 配置 ──────────────────────────────────────────────────────────


def _cfg(key: str, default: Any = "") -> Any:
    """读插件配置（三级链：env → 存储 → default）；缺失返回 default。"""
    try:
        value = PluginConfigStore().get(PLUGIN_NAME, key)
    except Exception as e:  # noqa: BLE001 — 主程序未注入存储时按默认走
        logger.debug(f"[vision-proxy] 读配置 {key} 失败（用默认）: {e}")
        return default
    return default if value is None else value


def _cfg_int(key: str, default: int, low: int, high: int) -> int:
    try:
        value = int(float(_cfg(key, default)))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


# ── 图片编码 ──────────────────────────────────────────────────────


def _encode_image(path: str) -> Tuple[str, str]:
    """图片 → multimodal 块；失败返回 ("", 错误说明)。"""
    raw = (path or "").strip()
    if not raw:
        return "", "空路径"
    if raw.startswith(("http://", "https://", "data:")):
        return raw, ""

    if not os.path.isfile(raw):
        return "", f"文件不存在: {raw}"
    ext = os.path.splitext(raw)[1].lower()
    mime = _MIME.get(ext)
    if mime is None:
        return "", f"不是受支持的图片格式（{ext or '无扩展名'}）: {raw}"
    try:
        size = os.path.getsize(raw)
        if size > _MAX_BYTES:
            return "", f"图片过大（{size // 1024 // 1024}MB > {_MAX_BYTES // 1024 // 1024}MB）: {raw}"
        with open(raw, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
    except OSError as e:
        return "", f"读取图片失败: {raw}（{e}）"
    return f"data:{mime};base64,{b64}", ""


def _build_user_content(question: str, urls: List[str]) -> List[Dict[str, Any]]:
    """OpenAI multimodal user content：文本块 + 图片块。"""
    blocks: List[Dict[str, Any]] = [{"type": "text", "text": question or _DEFAULT_QUESTION}]
    blocks.extend({"type": "image_url", "image_url": {"url": u}} for u in urls)
    return blocks


# ── 宿主能力 ──────────────────────────────────────────────────────


def _host_pool():
    """取 ui surface 能力池（engine.session / get_provider_config 都在这一面）。"""
    return pool_for(plugin=PLUGIN_NAME, surface="ui")


def _vision_override(provider: str, model: str) -> Tuple[Dict[str, Any], str]:
    """解析视觉模型的完整 llm_config（含明文 API_KEY）；失败返回 ({}, 错误)。"""
    if not provider and not model:
        return {}, "未配置视觉模型：请在插件设置里填「视觉服务商」或「视觉模型」"
    pool = _host_pool()
    if pool is None or "model.config" not in pool:
        return {}, "宿主未提供 model.config 能力（请升级 DriFox，或检查 manifest capabilities）"
    try:
        resolve = pool.legacy("get_provider_config", "model.config")
    except Exception as e:  # noqa: BLE001
        return {}, f"宿主未提供 get_provider_config 服务: {e}"
    if not callable(resolve):
        return {}, "宿主未提供 get_provider_config 服务"
    try:
        raw_cfg: Any = resolve(provider, model) or {}
    except Exception as e:  # noqa: BLE001
        return {}, f"解析视觉模型配置失败: {type(e).__name__}: {e}"
    if not isinstance(raw_cfg, dict) or not raw_cfg:
        return {}, f"找不到可用的服务商/模型配置（provider={provider or '当前'} model={model or '当前'}）"
    return {str(k): v for k, v in raw_cfg.items()}, ""


def _auto_pick_vision_model() -> Tuple[str, str, str]:
    """未显式配置时，自动挑一个声明支持图像的模型。

    走 provider.list → model.enumerate 两级：先用「当前服务商」里的视觉模型，
    没有再遍历其余服务商。supports_vision 由宿主的声明层（「声明_支持图像」
    六键 L0）给出，比按模型名猜（含 -vl / vision / 4o 等字样）可靠。

    Returns: (provider_id, model_name, error)；成功时 error 为空串。
    """
    pool = _host_pool()
    if pool is None or "provider.list" not in pool or "model.enumerate" not in pool:
        return "", "", "宿主未提供 provider.list / model.enumerate 能力（请升级 DriFox）"
    try:
        providers = pool["provider.list"]() or []
    except Exception as e:  # noqa: BLE001
        return "", "", f"枚举服务商失败: {type(e).__name__}: {e}"

    # 当前服务商优先（同一家不用换 key / 不用跨网关计费）
    ordered = sorted(providers, key=lambda p: 0 if p.get("is_current") else 1)
    for p in ordered:
        pid = str(p.get("id") or "")
        if not pid:
            continue
        try:
            models = pool["model.enumerate"](pid) or []
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[vision-proxy] 枚举 {pid} 模型失败（跳过）: {e}")
            continue
        for m in models:
            if m.get("supports_vision") and str(m.get("name") or ""):
                return pid, str(m["name"]), ""
    return "", "", (
        "未配置视觉模型，且当前所有服务商里找不到声明支持图像的模型。"
        "请在插件设置里手动指定，或先添加一个多模态模型的服务商。"
    )


def _create_session(override: Dict[str, Any]) -> Tuple[Any, str]:
    """创建引擎会话（隔离会话、不触发全局 hook、不给工具）；失败返回 (None, 错误)。"""
    pool = _host_pool()
    if pool is None or "engine.session" not in pool:
        return None, "宿主未提供 engine.session 能力（请升级 DriFox，或检查 manifest capabilities）"
    create = pool["engine.session"]
    if not callable(create):
        return None, "宿主未提供 create_engine_session 服务"
    try:
        return (
            create(
                ENGINE_NAME,
                model_config_override=override or None,
                hook_policy="none",
                permission_strategy="auto_deny",
            ),
            "",
        )
    except Exception as e:  # noqa: BLE001 — 常见于无活跃窗口（host=None）
        return None, f"创建对话引擎会话失败: {type(e).__name__}: {e}"


def _run_turn(session, messages: List[Dict[str, Any]], timeout: float):
    """在 daemon 线程里跑 turn()（带硬看门狗，避免 worker 卡死拖住工具）。

    turn() 内部有超时，但实测流式挂死时收尾链可能不执行；这里额外按
    timeout+缓冲 放弃等待并下发 cancel。
    """
    holder: Dict[str, Any] = {}
    done = threading.Event()

    def _worker():
        try:
            result = session.turn(messages=messages, tools=[], timeout=timeout)
            holder["result"] = result
        except Exception as e:  # noqa: BLE001 — 线程内异常不能静默吞
            holder["error"] = f"{type(e).__name__}: {e}"
        finally:
            done.set()

    threading.Thread(target=_worker, daemon=True, name="vision-proxy-turn").start()
    if not done.wait(timeout + 30.0):
        try:
            session.cancel()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[vision-proxy] cancel 失败（忽略）: {e}")
        return None, f"视觉模型超时（>{timeout:.0f}s），已取消"

    if "error" in holder:
        return None, str(holder["error"])
    result = holder.get("result")
    if result is None:
        return None, "视觉模型无返回"
    if getattr(result, "timed_out", False):
        return None, f"视觉模型超时（>{timeout:.0f}s）"
    if getattr(result, "cancelled", False):
        return None, "视觉模型调用被取消"
    err = getattr(result, "error", None)
    if err:
        return None, f"视觉模型返回错误: {err}"
    text = (getattr(result, "text", "") or "").strip()
    if not text:
        return None, "视觉模型返回空内容"
    return text, ""


# ── impl ──────────────────────────────────────────────────────────


def _impl(tool_ctx, **kwargs):
    raw_paths = kwargs.get("paths")
    if isinstance(raw_paths, str):
        raw_paths = [raw_paths]
    if not isinstance(raw_paths, (list, tuple)) or not raw_paths:
        return ToolResult(False, error="paths 不能为空：传入图片路径或 http(s) 图片 URL 的列表")

    max_images = _cfg_int("max_images", 4, 1, 8)
    paths = [str(p) for p in raw_paths if str(p or "").strip()]
    if len(paths) > max_images:
        return ToolResult(False, error=f"一次最多 {max_images} 张图片，本次给了 {len(paths)} 张")

    urls: List[str] = []
    for p in paths:
        url, err = _encode_image(p)
        if err:
            return ToolResult(False, error=err)
        urls.append(url)

    provider = str(_cfg("vision_provider", "") or "").strip()
    model = str(_cfg("vision_model", "") or "").strip()
    timeout = float(_cfg_int("timeout_sec", 120, 10, 600))

    if not provider and not model:
        # 未配置 → 自动挑一个声明支持图像的模型（当前服务商优先）
        provider, model, auto_err = _auto_pick_vision_model()
        if auto_err:
            return ToolResult(False, error=auto_err)

    override, err = _vision_override(provider, model)
    if err:
        return ToolResult(False, error=err)

    session, err = _create_session(override)
    if err:
        return ToolResult(False, error=err)

    question = str(kwargs.get("question") or "").strip()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_content(question, urls)},
    ]
    session_obj = session
    try:
        text, err = _run_turn(session_obj, messages, timeout)
    finally:
        try:
            session_obj.cleanup()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[vision-proxy] 会话清理失败（忽略）: {e}")

    if err:
        return ToolResult(False, error=err)

    used = str(override.get("模型名称", "") or "")
    header = f"[图片描述 · 由视觉模型 {used} 生成]\n" if used else "[图片描述]\n"
    return ToolResult(True, content=f"{header}{text or ''}")


def _preview(tool_args: dict) -> str:
    paths = tool_args.get("paths") or []
    if isinstance(paths, str):
        paths = [paths]
    n = len(paths) if isinstance(paths, (list, tuple)) else 0
    q = str(tool_args.get("question") or "").strip()
    return f"看图（{n} 张）" + (f"：{q[:40]}" if q else "")


_SCHEMA = {
    "type": "function",
    "function": {
        "name": "vision_describe",
        "description": (
            "图片代理：把图片交给支持多模态的模型识别，返回文字描述。"
            "当你的当前模型不支持视觉（看不到图片、只能拿到文件路径）时使用本工具，"
            "用返回的文字描述继续推理。支持本地图片路径与 http(s) 图片 URL，"
            "一次可传多张。传入 question 可指定想从图片里得到什么信息"
            "（如「提取图中的表格数据」「读出截图里的报错文字」）。"
            "当前模型本身支持视觉时不要调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "图片路径或 http(s) 图片 URL 列表，单张 ≤8MB",
                },
                "question": {
                    "type": "string",
                    "description": "想从图片中得到的信息；省略则描述全部可见内容",
                },
            },
            "required": ["paths"],
        },
    },
}


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    from app.plugins.sdk import make_summarize_from_preview

    registry.register(
        "vision_describe",
        _SCHEMA,
        impl=_impl,
        danger="safe",
        icon="vision_describe",
        cn_name="图片理解代理",
        group="多模态",
        description="把图片转发给多模态模型识别并取回文字描述",
        aliases=["VisionDescribe", "describe_image"],
        preview=_preview,
        summarize=make_summarize_from_preview(_preview),
    )
