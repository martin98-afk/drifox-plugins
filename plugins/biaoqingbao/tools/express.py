# -*- coding: utf-8 -*-
"""express — 助手用自己的情绪发表情包。

流程：情绪词 → 标签三档打分 → 偏好加减分 → top3 随机取一 → 返回 markdown 图片。
移植自 moononnn/DeepSeek-Harness-biaoqingbao（MIT）的 express 工具。
"""
from __future__ import annotations

import random
import re
import sys
from html import escape
from pathlib import Path

# 宿主 tools 加载器不注插件根，先自注入再 import 本插件包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.tools.registry import make_summarize_from_preview
from app.tools.result import ToolResult

from biaoqingbao_core import store
from biaoqingbao_core.scoring import collect_prefs_for_emotion, sanitize_tag, score_stickers

GROUP = "表情包"
MAX_RECENT = 5
# 进程内最近使用记录（session 维度；DriFox 工具无 session 句柄时退化为全局）
_recent: list[str] = []

# markdown 图片：![alt](path)
_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
# 自定义标记：[sticker:/abs/path] —— 模型不会把它当图片复述到正文
_STICKER_RE = re.compile(r"\[sticker:([^\]]+)\]")

_SCHEMA = {
    "type": "function",
    "function": {
        "name": "biaoqingbao_express",
        "description": (
            "用表情包表达你（助手）自己的情绪。当你回复用户时，如果自己感受到了开心、委屈、"
            "心疼、无奈、感动、得意、无语等情绪，想用一张图片表达感受，就调用这个工具。"
            "只需传一个情绪词，如 emotion='开心' 或 emotion='心疼想抱抱你'。"
            "这是助手自己的情绪表达方式，不是必须执行的任务；工作/严肃场景不要用。"
            "注意：工具返回的 [sticker:...] 标记是内部渲染指令，不要在回复正文里复述它或图片路径。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "emotion": {
                    "type": "string",
                    "description": "你想表达的情绪或感受，一个词或短句：开心、委屈、心疼、想抱抱你、得意、无语、感动、治愈、吃瓜、撒娇、社死、emo",
                },
                "exclude_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选：最近用过的表情包 ID，避免重复",
                },
            },
            "required": ["emotion"],
        },
    },
}


def _preview(args: dict) -> str:
    emo = (args or {}).get("emotion") or ""
    return f"表情：{emo}"


def _render_express_body(result, tool_name, tool_args, success):
    """express 完成框渲染闭包：把 markdown 图片显示成真实图片。

    签名与 desktop-automation 的 screenshot 一致：
    render(result, tool_name, tool_args, success) -> str | None
    返回 None 回退通用文本渲染（no_match / 错误场景）。
    """
    content = getattr(result, "content", "") or ""
    if not isinstance(content, str):
        content = str(content)
    # 优先自定义标记；兼容旧格式 markdown 图片
    m = _STICKER_RE.search(content)
    if m:
        path, alt = m.group(1).strip(), "表情"
        head = content[: m.start()].strip()
    else:
        m = _IMG_RE.search(content)
        if not m:
            return None
        alt, path = m.group(1), m.group(2)
        head = content[: m.start()].strip()
    note = (
        f'<span style="color:var(--text-secondary);font-size:12px;">{escape(head)}</span>'
        if head else ""
    )
    return (
        '<div style="display:flex;flex-direction:column;gap:8px;align-items:flex-start;padding:2px 0;">'
        f'<img src="{escape(path)}" alt="{escape(alt)}" '
        'style="max-width:180px;max-height:180px;border-radius:10px;display:block;" />'
        f'{note}'
        '</div>'
    )


def _impl(tool_ctx, **kwargs):
    emotion = sanitize_tag(kwargs.get("emotion"), 60)
    if not emotion:
        return ToolResult(False, error="请传入你想表达的情绪")

    data_dir = store.resolve_data_dir(tool_ctx)
    cfg = store.load_config(data_dir)
    if cfg.get("enabled") is False:
        return ToolResult(False, error="表情包功能已关闭（设置 → 插件 → 表情包）")

    stickers = store.load_stickers(data_dir)
    if not stickers:
        return ToolResult(
            False,
            error="表情包库是空的。让用户先往图库放几张图（或用 biaoqingbao_add_sticker 导入）",
        )

    prefs = store.load_prefs(data_dir)
    user_prefs = (prefs.get("users") or {}).get("default") or {"mappings": []}
    prefs_for = collect_prefs_for_emotion(user_prefs.get("mappings"), emotion)

    exclude = list(kwargs.get("exclude_ids") or []) + list(_recent)
    scored = score_stickers(stickers, emotion, exclude, prefs_for)
    if not scored:
        # 排除名单导致全空时，放开最近记录再试一次
        scored = score_stickers(stickers, emotion, list(kwargs.get("exclude_ids") or []), prefs_for)
    if not scored:
        return ToolResult(
            True,
            content=f"没有找到匹配「{emotion}」的表情包，可以换个情绪词，或先往图库加图。",
        )

    top = scored[: min(3, len(scored))]
    best = random.choice(top)
    _recent.append(best["id"])
    if len(_recent) > MAX_RECENT:
        _recent.pop(0)

    path = store.sticker_abs_path(data_dir, best)
    if not path:
        return ToolResult(False, error=f"表情包文件丢失：{best.get('file')}")

    desc = best.get("description") or best.get("id")
    # markdown 图片：宿主 _resolve_image_src 会把绝对路径转 file:/// 渲染
    # 用自定义标记而非 markdown 图片：模型看到 ![](...) 容易原样复述到正文，
    # 而正文图片宿主不限制尺寸（只有 max-width:100%），会撑满整行。
    content = f"已发送表情包「{desc}」（匹配度 {best['_score']}）\n\n[sticker:{path}]"
    return ToolResult(True, content=content, data={"sticker": {
        "id": best["id"], "description": desc, "score": best["_score"], "emotion": emotion,
    }})


def register(registry):
    registry.register(
        "biaoqingbao_express",
        _SCHEMA,
        impl=_impl,
        danger="safe",
        cn_name="发表情包",
        group=GROUP,
        description="按自己的情绪挑一张表情包发出来",
        render_mode="expand",  # 图片直接展示，禁用折叠框
        render=_render_express_body,
        keep_in_content=True,  # 表情卡常驻正文，不迁入「工具与思考」折叠区
        preview=_preview,
        summarize=make_summarize_from_preview(_preview),
    )
