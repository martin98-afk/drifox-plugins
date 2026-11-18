# -*- coding: utf-8 -*-
"""express — 助手用自己的情绪发表情包。

流程：情绪词 → 口语兜底扩展 → 标签三档打分 → 偏好加减分 → top3 随机取一
→ 生成 180px 缩略图 → 返回 markdown 图片（模型在正文复述）。
移植自 moononnn/DeepSeek-Harness-biaoqingbao（MIT）的 express 工具。

展示通道选择：正文 markdown 图片（宿主 _resolve_image_src 转 file:///）。
不走工具卡 body —— 简洁模式下宿主 lazy_body 只给 body 留空壳，靠「展开工具区」
时 JS 注入；卡片本身收在「工具与思考」折叠区。缩略图负责控宽：正文图片只有
max-width:100%，原图 618px 会撑满整行，缩略图的天然像素宽就是 180。
"""
from __future__ import annotations

import random
import sys
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

# 情绪口语兜底：内置图库导入后不会随 starter 更新，词表缺口在这里补
_ALIASES = {
    "得意": "开心 成功 干得漂亮",
    "心疼": "撒娇 抱抱",
    "想抱抱你": "撒娇 抱抱",
    "抱抱": "撒娇",
    "贴贴": "撒娇 可爱",
    "感动": "喜欢 爱了",
    "治愈": "喜欢 可爱",
    "吃瓜": "惊讶 好家伙",
    "emo": "难过 失落",
    "破防": "难过 崩溃",
    "无语": "无奈 服了",
    "爱你": "喜欢 爱心",
}

_SCHEMA = {
    "type": "function",
    "function": {
        "name": "biaoqingbao_express",
        "description": (
            "用表情包表达你（助手）自己的情绪。当你回复用户时，如果自己感受到了开心、委屈、"
            "心疼、无奈、感动、得意、无语等情绪，想用一张图片表达感受，就调用这个工具。"
            "只需传一个情绪词，如 emotion='开心' 或 emotion='心疼想抱抱你'。"
            "调用成功会返回一张 markdown 图片，请在你的回复正文中原样包含它（前面配一句短话即可）。"
            "这是助手自己的情绪表达方式，不是必须执行的任务；工作/严肃场景不要用。"
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
        # 首次使用：自动导入内置图库（只做一次，用户清空后不再自动填）
        store.ensure_starter_imported(
            data_dir, Path(__file__).resolve().parent.parent / "starter"
        )
        stickers = store.load_stickers(data_dir)
    if not stickers:
        return ToolResult(
            False,
            error="表情包库是空的。让用户先往图库放几张图（或用 biaoqingbao_add_sticker 导入）",
        )

    prefs = store.load_prefs(data_dir)
    user_prefs = (prefs.get("users") or {}).get("default") or {"mappings": []}
    prefs_for = collect_prefs_for_emotion(user_prefs.get("mappings"), emotion)

    # 口语词扩展：别名拼进查询串，靠标签包含匹配兜底（图库词表不全时也不落空）
    query = emotion
    alias = _ALIASES.get(emotion)
    if alias:
        query = f"{emotion} {alias}"

    exclude = list(kwargs.get("exclude_ids") or []) + list(_recent)
    scored = score_stickers(stickers, query, exclude, prefs_for)
    if not scored:
        # 排除名单导致全空时，放开最近记录再试一次
        scored = score_stickers(stickers, query, list(kwargs.get("exclude_ids") or []), prefs_for)
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

    path = store.thumb_path(data_dir, best)
    if path is None:
        return ToolResult(False, error=f"表情包文件丢失：{best.get('file')}")

    desc = best.get("description") or best.get("id")
    alt = sanitize_tag(desc, 30) or "表情包"
    content = (
        f"已发送表情包「{desc}」（匹配度 {best['_score']}）\n\n"
        f"![{alt}]({path})"
    )
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
        render_mode="inline",  # 单行卡：图片由回复正文承载，卡里不再渲染 body
        # 不进正文：卡收进「工具与思考」折叠区，正文只留模型复述的图片
        preview=_preview,
        summarize=make_summarize_from_preview(_preview),
    )
