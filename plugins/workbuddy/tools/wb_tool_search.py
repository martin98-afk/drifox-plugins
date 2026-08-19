# -*- coding: utf-8 -*-
"""workbuddy wb_tool_search — 按关键词搜索可用工具

适配说明：DriFox 的 `_PluginRegistryProxy` 只暴露 `register()`，不暴露
`list()`/`get()` 等读方法（防止插件越权查询全局注册表）。因此搜索范围限定为：
1. workbuddy 插件自身工具（register 时索引到本地 _TOOLS_INDEX）
2. DriFox 常见内置工具硬编码清单（与 DriFox 实际 builtin 工具集同步）

如需检索其他插件 / MCP 工具，请用 `list_skills` 或 `mcp_list_servers`。
"""
import sys
from pathlib import Path

_TOOLS_DIR = str(Path(__file__).resolve().parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from app.tools.registry import make_summarize_from_preview  # noqa: E402
from app.tools.result import ToolResult  # noqa: E402

GROUP = "工具发现"
_TOOLS_INDEX: list[dict] = []  # register 时填充
_DRIFOX_BUILTIN_TOOLS: list[dict] = [
    # 文件
    {"name": "read", "cn_name": "读文件", "description": "读文件（含文本/图片/目录列表，图片 base64）",
     "danger": "safe", "aliases": ["Read", "cat"]},
    {"name": "write", "cn_name": "写文件", "description": "创建或覆盖写入文件",
     "danger": "dangerous", "aliases": ["Write"]},
    {"name": "edit", "cn_name": "编辑文件", "description": "精确替换编辑文件内容",
     "danger": "dangerous", "aliases": ["Edit"]},
    {"name": "multi_edit", "cn_name": "多次编辑", "description": "对同一文件按顺序应用多个 edit",
     "danger": "dangerous", "aliases": ["MultiEdit"]},
    {"name": "grep", "cn_name": "内容搜索", "description": "在文件/目录中按正则搜索",
     "danger": "safe", "aliases": ["Grep"]},
    {"name": "list", "cn_name": "列目录", "description": "列出目录内容", "danger": "safe", "aliases": ["List"]},
    {"name": "glob", "cn_name": "通配匹配", "description": "按 glob 模式匹配文件路径",
     "danger": "safe", "aliases": ["Glob"]},
    {"name": "scan_repo", "cn_name": "扫描仓库", "description": "扫描仓库结构（深度可控）",
     "danger": "safe", "aliases": ["ScanRepo"]},
    {"name": "stage_files", "cn_name": "暂存文件", "description": "标记文件为待编辑（外部修改检测）",
     "danger": "safe", "aliases": ["StageFiles"]},
    # 命令
    {"name": "bash", "cn_name": "执行命令", "description": "执行 shell 命令（Windows 走 PowerShell）",
     "danger": "dangerous", "aliases": ["Bash"]},
    {"name": "bg_start", "cn_name": "启动后台", "description": "启动后台任务", "danger": "dangerous", "aliases": []},
    {"name": "bg_stop", "cn_name": "停止后台", "description": "停止后台任务", "danger": "safe", "aliases": []},
    {"name": "bg_logs", "cn_name": "后台日志", "description": "读取后台任务日志", "danger": "safe", "aliases": []},
    {"name": "bg_list", "cn_name": "后台列表", "description": "列出后台任务", "danger": "safe", "aliases": []},
    # 网络
    {"name": "websearch", "cn_name": "联网搜索", "description": "联网搜索关键词",
     "danger": "safe", "aliases": ["WebSearch"]},
    {"name": "webfetch", "cn_name": "抓取 URL", "description": "抓取 URL 内容（markdown 化）",
     "danger": "safe", "aliases": ["WebFetch"]},
    # 任务管理
    {"name": "todowrite", "cn_name": "写待办", "description": "创建/更新结构化待办",
     "danger": "safe", "aliases": ["TodoWrite"]},
    {"name": "todoread", "cn_name": "读待办", "description": "查看当前待办列表", "danger": "safe", "aliases": ["TodoRead"]},
    # 交互
    {"name": "question", "cn_name": "向用户提问", "description": "向用户提问以澄清歧义",
     "danger": "safe", "aliases": ["AskUserQuestion"]},
    {"name": "skill", "cn_name": "加载技能", "description": "加载指定技能（注入领域知识）",
     "danger": "safe", "aliases": ["Skill"]},
    {"name": "list_skills", "cn_name": "列技能", "description": "列出可用技能", "danger": "safe", "aliases": []},
    {"name": "mcp_list_servers", "cn_name": "列 MCP", "description": "列出已连接 MCP 服务器与工具",
     "danger": "safe", "aliases": []},
    {"name": "upload_file", "cn_name": "上传文件", "description": "上传文件到远端网关获取下载链接",
     "danger": "safe", "aliases": []},
    # 子代理
    {"name": "subagent_para", "cn_name": "并行子代理", "description": "并行派发多个子代理",
     "danger": "safe", "aliases": []},
    {"name": "subagent_dag", "cn_name": "DAG 子代理", "description": "DAG 工作流派发子代理",
     "danger": "safe", "aliases": []},
    {"name": "subagent_status", "cn_name": "子代理状态", "description": "查询后台子代理进度",
     "danger": "safe", "aliases": []},
    {"name": "team_send_message", "cn_name": "团队消息", "description": "向团队成员发消息",
     "danger": "safe", "aliases": []},
    {"name": "team_list_members", "cn_name": "团队成员", "description": "列出团队成员",
     "danger": "safe", "aliases": []},
    # 诊断
    {"name": "get_diagnostics", "cn_name": "诊断", "description": "获取文件/项目的诊断信息（错误/警告）",
     "danger": "safe", "aliases": []},
    {"name": "lsp", "cn_name": "LSP", "description": "调用语言服务器（hover/引用/定义等）",
     "danger": "safe", "aliases": []},
    # workbuddy 插件自身工具（在 register() 调用时索引到 _TOOLS_INDEX）
]


def _score(entry: dict, q: str) -> int:
    """对工具条目按关键词命中位置加权评分"""
    if not q:
        return 0
    score = 0
    if q in entry.get("name", "").lower():
        score += 5
    if entry.get("cn_name") and q in entry["cn_name"].lower():
        score += 3
    for alias in entry.get("aliases") or []:
        if q in alias.lower():
            score += 3
    if entry.get("description") and q in entry["description"].lower():
        score += 1
    return score


def _search_impl(tool_ctx, **kwargs):
    query_raw = (kwargs.get("query") or "").strip()
    if not query_raw:
        return ToolResult(False, error="query 不能为空")
    q = query_raw.lower()
    try:
        limit = max(1, min(int(kwargs.get("limit") or 10), 50))
    except (TypeError, ValueError):
        limit = 10

    # 合并 workbuddy 插件工具 + DriFox builtin 硬编码清单
    pool = list(_DRIFOX_BUILTIN_TOOLS) + list(_TOOLS_INDEX)
    matches = [(s, e) for s, e in ((_score(e, q), e) for e in pool) if s > 0]
    matches.sort(key=lambda x: (-x[0], x[1].get("name", "")))

    if not matches:
        return ToolResult(
            True,
            content=(
                f"## 未找到匹配 `{query_raw}` 的工具\n\n"
                f"搜索范围：workbuddy 插件工具 + DriFox 常见内置工具（不含其他插件/MCP）。"
                f"试试同义词或更短的关键词；其他插件工具请用 `list_skills`，MCP 工具请用 `mcp_list_servers`。"
            ),
        )

    lines = [f"## 工具搜索：`{query_raw}`（命中 {len(matches)} 条，展示 {limit} 条）", ""]
    lines.append("| # | 工具名 | 级别 | 中文名 | 描述 | 别名 |")
    lines.append("|---|--------|------|--------|------|------|")
    for idx, (score, reg) in enumerate(matches[:limit], 1):
        aliases = ", ".join(reg.get("aliases", [])[:3]) or "—"
        cn = reg.get("cn_name") or "—"
        desc = (reg.get("description") or "")[:60]
        danger = "🔴 危险" if reg.get("danger") == "dangerous" else "🟢 安全"
        lines.append(f"| {idx} | `{reg.get('name')}` | {danger} | {cn} | {desc} | {aliases} |")
    lines.append("")
    lines.append("_注：本工具只能搜索 workbuddy 插件工具 + DriFox 常见内置工具；其他插件/MCP 工具请用 `list_skills` / `mcp_list_servers`。_")
    return ToolResult(True, content="\n".join(lines))


def _preview(tool_args: dict) -> str:
    q = (tool_args or {}).get("query", "")
    return f"搜工具：`{q}`"


_SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "wb_tool_search",
        "description": (
            "按关键词搜索可用工具。范围：workbuddy 插件工具 + DriFox 常见内置工具。"
            "不确定工具名/中文名/别名时调用；其他插件/MCP 工具请用 list_skills / mcp_list_servers。"
        ),
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
    """注册 wb_tool_search 并把自身索引到本地 _TOOLS_INDEX"""
    registry.register(
        "wb_tool_search", _SEARCH_SCHEMA, impl=_search_impl,
        danger="safe", icon="tool_search", cn_name="搜工具",
        group=GROUP, description="按关键词搜索可用工具",
        aliases=["tool_search", "ToolSearch", "search_tool"],
        render_mode="expand",
        preview=_preview,
        summarize=make_summarize_from_preview(_preview),
    )
    # 把自身索引到 _TOOLS_INDEX，供 _search_impl 检索
    _TOOLS_INDEX.append({
        "name": "wb_tool_search",
        "cn_name": "搜工具",
        "description": "按关键词搜索可用工具（workbuddy + DriFox 常见内置）",
        "danger": "safe",
        "aliases": ["tool_search", "ToolSearch", "search_tool"],
    })