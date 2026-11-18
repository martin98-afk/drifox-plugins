# -*- coding: utf-8 -*-
"""图库管理 — 合并为一个 biaoqingbao_manage(action=...)。

原 6 个独立工具（search/list/add_sticker/update_tags/feedback/import_starter）
每轮随 prompt 走约 2400 字符 schema；合并后约 800，省一半以上。
各 action 的实现与合并前逐字一致，只是入口变参数分发。
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
ACTIONS = ("list", "search", "add", "update_tags", "feedback", "import_starter")

_SCHEMA = {
    "type": "function",
    "function": {
        "name": "biaoqingbao_manage",
        "description": (
            "图库管理。action：list 列全部；search 按词搜(query)；add 导本地图(path)；"
            "update_tags 改标签(id)；feedback 记喜欢/不喜欢(id+context)；import_starter 导内置 39 张。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": list(ACTIONS),
                    "description": "要做的事",
                },
                "query": {"type": "string", "description": "search：搜索词"},
                "limit": {"type": "integer", "description": "search：返回条数，默认 10"},
                "path": {"type": "string", "description": "add：本地图片绝对路径，8MB 内"},
                "description": {"type": "string", "description": "add/update_tags：一句话描述"},
                "id": {"type": "string", "description": "update_tags/feedback：表情包 ID"},
                "emotion": {
                    "type": "array", "items": {"type": "string"},
                    "description": "add/update_tags：情绪标签，整体替换",
                },
                "scene": {
                    "type": "array", "items": {"type": "string"},
                    "description": "add/update_tags：场景标签，整体替换",
                },
                "keywords": {
                    "type": "array", "items": {"type": "string"},
                    "description": "add/update_tags：关键词，整体替换",
                },
                "context": {"type": "string", "description": "feedback：当时想表达的情绪"},
                "positive": {"type": "boolean", "description": "feedback：true=喜欢，false=不喜欢"},
            },
            "required": ["action"],
        },
    },
}


def _list(data_dir: Path) -> ToolResult:
    stickers = store.load_stickers(data_dir)
    if not stickers:
        return ToolResult(True, content="图库是空的。可以用 action=add 导入图片，或 action=import_starter 导入内置图库。")
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


def _search(data_dir: Path, query, limit) -> ToolResult:
    q = sanitize_tag(query, 60)
    if not q:
        return ToolResult(False, error="search 需要 query")
    n = max(1, min(int(limit or 10), 50))
    stickers = store.load_stickers(data_dir)
    if not stickers:
        return ToolResult(True, content="图库是空的。")

    hits = score_stickers(stickers, q, [], {"preferred": [], "vetoed": [], "dislikes": {}})
    if not hits:
        hits = [{**s, "_score": 1} for s in substring_match(stickers, q)]
    if not hits:
        return ToolResult(True, content=f"没有找到匹配「{q}」的表情包。")

    lines = [f"找到 {min(len(hits), n)} 张（共 {len(hits)}）："]
    for s in hits[:n]:
        tags = s.get("tags") or {}
        emo = "/".join(tags.get("emotion") or []) or "-"
        lines.append(f"- {s.get('id')}｜{s.get('description') or '-'}｜情绪 {emo}｜分数 {s['_score']}")
    return ToolResult(True, content="\n".join(lines))


def _add(data_dir: Path, kwargs: dict) -> ToolResult:
    raw_path = (kwargs.get("path") or "").strip()
    if not raw_path:
        return ToolResult(False, error="add 需要 path")
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


def _update_tags(data_dir: Path, kwargs: dict) -> ToolResult:
    sid = sanitize_tag(kwargs.get("id"), 60)
    if not sid:
        return ToolResult(False, error="update_tags 需要 id")
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


def _feedback(data_dir: Path, kwargs: dict) -> ToolResult:
    sid = sanitize_tag(kwargs.get("id"), 60)
    ctx_emotion = sanitize_tag(kwargs.get("context"), 60)
    if not ctx_emotion:
        emos = str_arr(kwargs.get("emotion"))
        ctx_emotion = emos[0] if emos else ""
    if not sid or not ctx_emotion:
        return ToolResult(False, error="feedback 需要 id 与 context（当时情绪）")
    store.record_feedback(data_dir, emotion=ctx_emotion, sticker_id=sid, positive=bool(kwargs.get("positive")))
    verdict = "喜欢" if kwargs.get("positive") else "不喜欢"
    return ToolResult(True, content=f"已记录：{sid} 在「{ctx_emotion}」情境下标记为{verdict}。")


def _starter(data_dir: Path) -> ToolResult:
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


def _impl(tool_ctx, **kwargs):
    action = sanitize_tag(kwargs.get("action"), 30)
    if action not in ACTIONS:
        return ToolResult(False, error=f"action 需为 {'/'.join(ACTIONS)} 之一")
    data_dir = store.resolve_data_dir(tool_ctx)
    if action == "list":
        return _list(data_dir)
    if action == "search":
        return _search(data_dir, kwargs.get("query"), kwargs.get("limit"))
    if action == "add":
        return _add(data_dir, kwargs)
    if action == "update_tags":
        return _update_tags(data_dir, kwargs)
    if action == "feedback":
        return _feedback(data_dir, kwargs)
    return _starter(data_dir)


def _preview(args: dict) -> str:
    a = (args or {}).get("action") or ""
    if a == "search":
        return f"搜索：{(args or {}).get('query') or ''}"
    if a == "add":
        return f"导入：{Path((args or {}).get('path') or '').name}"
    if a == "update_tags":
        return f"改标签：{(args or {}).get('id') or ''}"
    if a == "feedback":
        verdict = "喜欢" if (args or {}).get("positive") else "不喜欢"
        return f"反馈{verdict}：{(args or {}).get('id') or ''}"
    if a == "list":
        return "列出图库"
    if a == "import_starter":
        return "导入内置图库"
    return "图库管理"


def register(registry):
    registry.register(
        "biaoqingbao_manage",
        _SCHEMA,
        impl=_impl,
        danger="safe",
        cn_name="表情包图库",
        group=GROUP,
        description="管理表情包图库：查看、搜索、导入、改标签、反馈",
        preview=_preview,
        summarize=make_summarize_from_preview(_preview),
    )
