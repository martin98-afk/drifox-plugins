# -*- coding: utf-8 -*-
"""图库管理工具组 — 搜索 / 列表 / 导入 / 改标签 / 反馈。

对应上游 search_stickers、list_stickers、add_sticker(HTTP 上传改为本地路径)、
update_sticker_tags、report_bad_match 五个工具。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 宿主 tools 加载器不注插件根，先自注入再 import 本插件包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.tools.registry import make_summarize_from_preview
from app.tools.result import ToolResult

from biaoqingbao_core import store
from biaoqingbao_core.scoring import (
    sanitize_tag,
    score_stickers,
    str_arr,
    substring_match,
)

GROUP = "表情包"


# ═══════════════ 搜索 ═══════════════

_SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "biaoqingbao_search",
        "description": "搜索表情包图库（管理用途）。按情绪/描述/标签找图，返回候选列表与 ID。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索词，如「开心」「猫咪」"},
                "limit": {"type": "integer", "description": "返回条数，默认 10", "default": 10},
            },
            "required": ["query"],
        },
    },
}


def _search_impl(tool_ctx, **kwargs):
    query = sanitize_tag(kwargs.get("query"), 60)
    limit = max(1, min(int(kwargs.get("limit") or 10), 50))
    data_dir = store.resolve_data_dir(tool_ctx)
    stickers = store.load_stickers(data_dir)
    if not stickers:
        return ToolResult(True, content="图库是空的。")

    hits = score_stickers(stickers, query, [], {"preferred": [], "vetoed": [], "dislikes": {}})
    if not hits:
        hits = [{**s, "_score": 1} for s in substring_match(stickers, query)]
    if not hits:
        return ToolResult(True, content=f"没有找到匹配「{query}」的表情包。")

    lines = [f"找到 {min(len(hits), limit)} 张（共 {len(hits)}）："]
    for s in hits[:limit]:
        tags = s.get("tags") or {}
        emo = "/".join(tags.get("emotion") or []) or "-"
        lines.append(f"- {s.get('id')}｜{s.get('description') or '-'}｜情绪 {emo}｜分数 {s['_score']}")
    return ToolResult(True, content="\n".join(lines))


# ═══════════════ 列表 ═══════════════

_LIST_SCHEMA = {
    "type": "function",
    "function": {
        "name": "biaoqingbao_list",
        "description": "列出表情包图库的全部图片与标签（管理用途）。",
        "parameters": {"type": "object", "properties": {}},
    },
}


def _list_impl(tool_ctx, **kwargs):
    data_dir = store.resolve_data_dir(tool_ctx)
    stickers = store.load_stickers(data_dir)
    if not stickers:
        return ToolResult(True, content="图库是空的。可以先用 biaoqingbao_add_sticker 导入图片。")
    lines = [f"图库共 {len(stickers)} 张："]
    for s in stickers:
        tags = s.get("tags") or {}
        parts = []
        for key in ("emotion", "scene", "keywords"):
            vals = tags.get(key) or []
            if vals:
                parts.append(f"{key}={'/'.join(str(v) for v in vals)}")
        lines.append(f"- {s.get('id')}｜{s.get('description') or '-'}｜{'；'.join(parts) or '无标签'}")
    return ToolResult(True, content="\n".join(lines))


# ═══════════════ 导入 ═══════════════

_ADD_SCHEMA = {
    "type": "function",
    "function": {
        "name": "biaoqingbao_add_sticker",
        "description": (
            "把一张本地图片导入表情包图库。支持 png/jpg/jpeg/gif/webp/bmp，单图 8MB 以内。"
            "导入时给情绪标签，后续 express 才能按情绪命中。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "本地图片绝对路径"},
                "description": {"type": "string", "description": "一句话描述这张图，如「开心猫咪挥手」"},
                "emotion": {
                    "type": "array", "items": {"type": "string"},
                    "description": "情绪标签，如 [\"开心\"] 或 [\"委屈\",\"想哭\"]",
                },
                "scene": {
                    "type": "array", "items": {"type": "string"},
                    "description": "使用场景，如 [\"问候\",\"早安\"]",
                },
                "keywords": {
                    "type": "array", "items": {"type": "string"},
                    "description": "关键词，如 [\"猫咪\",\"挥手\"]",
                },
            },
            "required": ["path"],
        },
    },
}


def _add_impl(tool_ctx, **kwargs):
    raw_path = (kwargs.get("path") or "").strip()
    if not raw_path:
        return ToolResult(False, error="请提供图片路径")
    data_dir = store.resolve_data_dir(tool_ctx)
    try:
        sticker = store.import_image(
            data_dir,
            Path(raw_path),
            description=sanitize_tag(kwargs.get("description"), 120),
            tags={
                "emotion": str_arr(kwargs.get("emotion")),
                "scene": str_arr(kwargs.get("scene")),
                "keywords": str_arr(kwargs.get("keywords")),
            },
        )
    except (FileNotFoundError, ValueError) as e:
        return ToolResult(False, error=str(e))
    return ToolResult(
        True,
        content=f"已导入：{sticker['id']}｜{sticker['description']}",
        data={"sticker": sticker},
    )


# ═══════════════ 改标签 ═══════════════

_UPDATE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "biaoqingbao_update_tags",
        "description": "修改某张表情包的描述或标签（管理用途）。只传要改的字段。",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "表情包 ID（biaoqingbao_list 可查）"},
                "description": {"type": "string", "description": "新描述"},
                "emotion": {"type": "array", "items": {"type": "string"}, "description": "新情绪标签（整体替换）"},
                "scene": {"type": "array", "items": {"type": "string"}, "description": "新场景标签（整体替换）"},
                "keywords": {"type": "array", "items": {"type": "string"}, "description": "新关键词（整体替换）"},
            },
            "required": ["id"],
        },
    },
}


def _update_impl(tool_ctx, **kwargs):
    sid = sanitize_tag(kwargs.get("id"), 60)
    if not sid:
        return ToolResult(False, error="请提供表情包 ID")
    data_dir = store.resolve_data_dir(tool_ctx)
    tags = {}
    for key in ("emotion", "scene", "keywords"):
        if key in kwargs and kwargs[key] is not None:
            tags[key] = str_arr(kwargs[key])
    updated = store.update_sticker(
        data_dir,
        sid,
        description=sanitize_tag(kwargs.get("description"), 120) if kwargs.get("description") is not None else None,
        tags=tags or None,
    )
    if not updated:
        return ToolResult(False, error=f"未找到表情包 {sid}")
    return ToolResult(True, content=f"已更新 {sid}｜{updated.get('description') or '-'}", data={"sticker": updated})


# ═══════════════ 反馈 ═══════════════

_FEEDBACK_SCHEMA = {
    "type": "function",
    "function": {
        "name": "biaoqingbao_feedback",
        "description": (
            "记录用户对某张表情包的反馈，影响以后的选择：喜欢会加分，不喜欢会否决并逐次降权。"
            "用户说「这个我喜欢」「这张不合适」时调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "表情包 ID"},
                "emotion": {"type": "string", "description": "当时想表达的情绪"},
                "positive": {"type": "boolean", "description": "true=喜欢，false=不喜欢"},
            },
            "required": ["id", "emotion", "positive"],
        },
    },
}


def _feedback_impl(tool_ctx, **kwargs):
    sid = sanitize_tag(kwargs.get("id"), 60)
    emotion = sanitize_tag(kwargs.get("emotion"), 60)
    positive = bool(kwargs.get("positive"))
    if not sid or not emotion:
        return ToolResult(False, error="需要 id 和 emotion")
    data_dir = store.resolve_data_dir(tool_ctx)
    store.record_feedback(data_dir, emotion=emotion, sticker_id=sid, positive=positive)
    verdict = "喜欢" if positive else "不喜欢"
    return ToolResult(True, content=f"已记录：{sid} 在「{emotion}」情境下标记为{verdict}。")


# ═══════════════ 导入内置图库 ═══════════════

_STARTER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "biaoqingbao_import_starter",
        "description": (
            "把插件自带的内置图库（13 类情绪、39 张 OpenMoji 表情）一键导入。"
            "图库为空时用它开箱可用；已导入过的会跳过，可重复执行。"
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}


def _starter_impl(tool_ctx, **kwargs):
    data_dir = store.resolve_data_dir(tool_ctx)
    pack_dir = Path(__file__).resolve().parent.parent / "starter"
    if not pack_dir.is_dir():
        return ToolResult(False, error=f"内置图库不存在：{pack_dir}")
    result = store.import_starter_pack(data_dir, pack_dir)
    if result.get("error"):
        return ToolResult(False, error=result["error"])
    total = len(store.load_stickers(data_dir))
    return ToolResult(
        True,
        content=f"内置图库导入完成：新增 {result['added']} 张，跳过 {result['skipped']} 张；当前图库共 {total} 张。",
    )


# ═══════════════ 注册 ═══════════════

def _preview_search(args: dict) -> str:
    return f"搜索：{(args or {}).get('query') or ''}"


def _preview_add(args: dict) -> str:
    return f"导入：{Path((args or {}).get('path') or '').name}"


def _preview_update(args: dict) -> str:
    return f"改标签：{(args or {}).get('id') or ''}"


def _preview_feedback(args: dict) -> str:
    verdict = "喜欢" if (args or {}).get("positive") else "不喜欢"
    return f"反馈{verdict}：{(args or {}).get('id') or ''}"


def register(registry):
    registry.register(
        "biaoqingbao_search", _SEARCH_SCHEMA, impl=_search_impl,
        danger="safe", cn_name="搜表情包", group=GROUP,
        description="按情绪或标签搜索图库",
        render_mode="expand", preview=_preview_search,
        summarize=make_summarize_from_preview(_preview_search),
    )
    registry.register(
        "biaoqingbao_list", _LIST_SCHEMA, impl=_list_impl,
        danger="safe", cn_name="表情包列表", group=GROUP,
        description="列出图库全部表情包",
        render_mode="expand", preview=lambda a: "列出图库",
        summarize=make_summarize_from_preview(lambda a: "列出图库"),
    )
    registry.register(
        "biaoqingbao_add_sticker", _ADD_SCHEMA, impl=_add_impl,
        danger="safe", cn_name="导入表情包", group=GROUP,
        description="把本地图片导入图库",
        render_mode="expand", preview=_preview_add,
        summarize=make_summarize_from_preview(_preview_add),
    )
    registry.register(
        "biaoqingbao_update_tags", _UPDATE_SCHEMA, impl=_update_impl,
        danger="safe", cn_name="改表情包标签", group=GROUP,
        description="修改表情包描述与标签",
        render_mode="expand", preview=_preview_update,
        summarize=make_summarize_from_preview(_preview_update),
    )
    registry.register(
        "biaoqingbao_feedback", _FEEDBACK_SCHEMA, impl=_feedback_impl,
        danger="safe", cn_name="表情包反馈", group=GROUP,
        description="记录喜欢/不喜欢，影响后续选图",
        render_mode="inline", preview=_preview_feedback,
        summarize=make_summarize_from_preview(_preview_feedback),
    )
    registry.register(
        "biaoqingbao_import_starter", _STARTER_SCHEMA, impl=_starter_impl,
        danger="safe", cn_name="导入内置表情包", group=GROUP,
        description="一键导入 39 张内置 OpenMoji 表情",
        render_mode="inline", preview=lambda a: "导入内置图库",
        summarize=make_summarize_from_preview(lambda a: "导入内置图库"),
    )
