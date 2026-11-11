# -*- coding: utf-8 -*-
"""AI 纪要生成：把转写稿交给大模型产出结构化纪要。

模型来源：
- 配置留空 → 跟随当前窗口/系统配置的模型（不传 override）
- 配置填了 provider:model / model → 经宿主 model.config 解析出完整配置再传 override

插件不单独保存 LLM 密钥：ASR 的硅基流动 Key 与 LLM 的 Key 是两回事。

线程约定：create_session() 必须在主线程调用（要解析窗口宿主），
generate_summary() 可在后台线程执行 turn()。
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

PLUGIN_NAME = "meeting-notes"
ENGINE_NAME = "meeting-notes"

# 转写稿字符上限。1 小时会议约 1.5 万字，6 万字足够容纳 3~4 小时；
# 超出截断并在提示词里注明，避免把上下文撑爆。
MAX_TRANSCRIPT_CHARS = 60000

# 默认超时；实际值由配置 summary_timeout_sec 注入，常量只作调用方缺省兜底
SUMMARY_TIMEOUT_SEC = 180.0

SYSTEM_PROMPT = (
    "你是专业会议记录员。只依据用户提供的转写稿写作，不补充外部知识，"
    "不编造人名、数字与决定；转写不清的地方如实标注。输出简体中文 Markdown。"
)

_USER_TEMPLATE = """下面是一场会议的语音转写稿。它来自语音识别，可能有错别字、漏字，说话人编号也可能不准。

请输出会议纪要。格式要求：

第一行用 `# 短标题` 给出会议标题（不超过 20 字，不加引号），
然后严格按以下结构写正文（不要加开场白、不要加总结性结尾）：

## 一句话概要
不超过 60 字。

## 关键讨论
- 按议题分条，每条写清结论和支撑它的关键事实/数字

## 决议
- 明确拍板的决定；没有就写「无」

## 待办
- 事项 —— 负责人 —— 期限（不确定的写「待定」）；没有就写「无」

## 风险与分歧
- 未达成一致的点、依赖外部条件的风险；没有就写「无」

转写稿：
---
{transcript}
---"""

# 暴露给设置卡展示用的同一份内置模板（唯一事实源，避免两处漂移）
DEFAULT_PROMPT_TEMPLATE = _USER_TEMPLATE

# 自定义模板里没提到标题时的补充要求
_TITLE_HINT = "\n\n另外：第一行请用 `# 短标题` 给出不超过 20 字的会议标题。"


def split_title(text: str) -> Tuple[str, str]:
    """从模型输出里抽出 `# 标题` 首行。返回 (标题, 正文)；无标题时标题为空串。"""
    lines = (text or "").strip().splitlines()
    if lines:
        first = lines[0].strip()
        if first.startswith("# ") and not first.startswith("## "):
            title = first[2:].strip().strip("`*_《》\"' ")
            body = "\n".join(lines[1:]).lstrip()
            return title[:40], body
    return "", (text or "").strip()


def build_transcript_text(meeting) -> Tuple[str, bool]:
    """会议 → 给模型的对话稿。返回 (文本, 是否被截断)。"""
    lines: List[str] = []
    for seg in meeting.segments:
        text = (seg.text or "").strip()
        if not text:
            continue
        label = meeting.speaker_label(seg.speaker) or "发言"
        lines.append(f"{label}: {text}")
    full = "\n".join(lines)
    if len(full) <= MAX_TRANSCRIPT_CHARS:
        return full, False
    return full[:MAX_TRANSCRIPT_CHARS] + "\n…（转写过长，已截断）", True


def build_messages(meeting, custom_template: str = "") -> List[Dict[str, str]]:
    """组装消息。custom_template 支持 {transcript} 占位符；无占位符则把转写稿接在末尾。"""
    transcript, truncated = build_transcript_text(meeting)
    if not transcript.strip():
        raise ValueError("这场会议还没有转写内容，无法生成纪要")

    tpl = (custom_template or "").strip()
    if tpl:
        if "{transcript}" in tpl:
            user = tpl.replace("{transcript}", transcript)
        else:
            user = f"{tpl}\n\n转写稿：\n---\n{transcript}\n---"
        if "# " not in tpl:
            user += _TITLE_HINT
    else:
        user = _USER_TEMPLATE.format(transcript=transcript)

    if truncated:
        user = "（注意：转写稿被截断，纪要只覆盖前半部分）\n\n" + user

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _resolve_model_override(spec: str) -> Optional[Dict[str, Any]]:
    """把 provider:model 配置解析成宿主可用的完整模型配置（含明文 key）。

    走 model.config_for 按名五级解析（「服务商:模型 / 服务商 / 模型名」，
    capability_type 缺省 chat）。旧 model.config 带参是 config_id 匹配、
    空 config_id 忽略 model，语义不符，不走。
    """
    spec = (spec or "").strip()
    if not spec:
        return None

    from app.plugins.sdk import pool_for

    pool = pool_for(plugin=PLUGIN_NAME, surface="ui")
    if pool is None or "model.config_for" not in pool:
        raise RuntimeError("宿主未提供 model.config_for 能力，无法解析指定模型")
    resolve = pool["model.config_for"]
    if not callable(resolve):
        raise RuntimeError("宿主未提供 model.config_for 能力")
    cfg = resolve(spec) or {}
    if not isinstance(cfg, dict) or not cfg:
        raise RuntimeError(f"找不到模型配置：{spec}（检查服务商与模型名）")
    return {str(k): v for k, v in cfg.items()}


def create_session(model_spec: str = ""):
    """创建引擎会话。必须在主线程调用。失败抛 RuntimeError（消息已人话化）。"""
    from app.plugins.sdk import pool_for

    pool = pool_for(plugin=PLUGIN_NAME, surface="ui")
    if pool is None or "engine.session" not in pool:
        raise RuntimeError("宿主未提供 engine.session 能力（请升级 DriFox）")
    create = pool["engine.session"]
    if not callable(create):
        raise RuntimeError("宿主未提供 create_engine_session 服务")

    override = _resolve_model_override(model_spec)
    try:
        return create(
            ENGINE_NAME,
            model_config_override=override,
            hook_policy="none",
            permission_strategy="auto_deny",
        )
    except Exception as e:  # noqa: BLE001 — 常见于无活跃窗口
        raise RuntimeError(f"创建对话引擎会话失败：{type(e).__name__}: {e}") from e


def generate_summary(
    session,
    meeting,
    custom_template: str = "",
    timeout: float = SUMMARY_TIMEOUT_SEC,
) -> str:
    """在后台线程执行一轮 turn() 产出纪要。失败抛 RuntimeError。"""
    messages = build_messages(meeting, custom_template)

    holder: Dict[str, Any] = {}
    done = threading.Event()

    def _worker() -> None:
        try:
            holder["result"] = session.turn(messages=messages, tools=[], timeout=timeout)
        except Exception as e:  # noqa: BLE001 — 线程内异常必须带回主线程
            holder["error"] = f"{type(e).__name__}: {e}"
        finally:
            done.set()

    threading.Thread(target=_worker, daemon=True, name="meeting-notes-summary").start()
    if not done.wait(timeout + 20.0):
        try:
            session.cancel()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[meeting-notes] cancel 失败（忽略）: {e}")
        raise RuntimeError(f"纪要生成超时（>{timeout:.0f}s）")

    if "error" in holder:
        raise RuntimeError(f"大模型调用失败：{holder['error']}")
    result = holder.get("result")
    if result is None:
        raise RuntimeError("大模型没有返回内容")
    if getattr(result, "timed_out", False):
        raise RuntimeError("大模型调用超时")
    if getattr(result, "cancelled", False):
        raise RuntimeError("纪要生成被取消")
    err = getattr(result, "error", None)
    if err:
        raise RuntimeError(f"大模型返回错误：{err}")
    text = (getattr(result, "text", "") or "").strip()
    if not text:
        raise RuntimeError("大模型返回了空内容")
    logger.info(f"[meeting-notes] 纪要生成完成：{len(text)} 字")
    return text
