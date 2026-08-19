# -*- coding: utf-8 -*-
"""workbuddy wb_tool_search — 按关键词搜索可用工具

模型不确定某个工具是否存在 / 别名是什么时调用，避免凭印象调用不存在的工具。
实现要点：
- register() 时缓存 registry 引用，供 impl 阶段查询
- 按 name/cn_name/aliases/description 加权评分匹配
"""
import sys
from pathlib import Path

_TOOLS_DIR = str(Path(__file__).resolve().parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from app.tools.registry import make_summarize_from_preview  # noqa: E402
from app.tools.result import ToolResult  # noqa: E402

GROUP = "工具发现"
_REGISTRY_REF = None


def _score(reg, q: str) -> int:
    if not q:
        return 0
    score = 0
    if q in reg.name.lower():
        score += 5
    if reg.cn_name and q in reg.cn_name.lower():
        score += 3
    for alias in reg.aliases or []:
        if q in alias.lower():
            score += 3
    if reg.description and q in reg.description.lower():
        score += 1
    return score


def _search_impl(tool_ctx, **kwargs):
    if _REGISTRY_REF is None:
        return ToolResult(False, error="registry 未初始化")
    query = (kwargs.get("query") or "").strip().lower()
    if not query:
        return ToolResult(False, error="query 不能为空")
    try:
        limit = max(1, min(int(kwargs.get("limit") or 10), 50))
    except (TypeError, ValueError):
        limit = 10

    matches = [(s, r) for s, r in ((_score(r, query), r) for r in _REGISTRY_REF.list()) if s > 0]
    matches.sort(key=lambda x: (-x[0], x[1].name))

    if not matches:
        return ToolResult(True, content=f"## 未找到匹配 `{query}` 的工具\n\n试试更短的关键词或同义词。")

    lines = [f"## 工具搜索：`{kwargs.get('query')}`（命中 {len(matches)} 条，本会话展示 {limit} 条）", ""]
    lines.append("| # | 工具名 | 级别 | 中文名 | 描述 | 别名 |")
    lines.append("|---|--------|------|--------|------|------|")
    for idx, (score, reg) in enumerate(matches[:limit], 1):
        aliases = ", ".join(reg.aliases[:3]) if reg.aliases else "—"
        cn = reg.cn_name or "—"
        desc = (reg.description or "")[:60]
        danger = "🔴 危险" if reg.danger == "dangerous" else "🟢 安全"
        lines.append(f"| {idx} | `{reg.name}` | {danger} | {cn} | {desc} | {aliases} |")
    return ToolResult(True, content="\n".join(lines))


def _preview(tool_args: dict) -> str:
    q = (tool_args or {}).get("query", "")
    return f"搜工具：`{q}`"


_SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "wb_tool_search",
        "description": "按关键词搜索可用工具。不确定工具名/别名时调用，返回工具名、危险级别、中文名、描述与别名，避免凭印象调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词（中英文、别名、子串均可）"},
                "limit": {"type": "integer", "description": "返回数量上限（1–50，默认 10）", "default": 10},
            },
            "required": ["query"],
        },
    },
}


def register(registry):
    """注册 wb_tool_search + 缓存 registry 引用"""
    global _REGISTRY_REF
    _REGISTRY_REF = registry
    registry.register(
        "wb_tool_search", _SEARCH_SCHEMA, impl=_search_impl,
        danger="safe", icon="tool_search", cn_name="搜工具",
        group=GROUP, description="按关键词搜索可用工具",
        aliases=["tool_search", "ToolSearch", "search_tool"],
        render_mode="expand",
        preview=_preview,
        summarize=make_summarize_from_preview(_preview),
    )