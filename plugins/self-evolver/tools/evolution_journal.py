# -*- coding: utf-8 -*-
"""
evolution_journal — 自进化工具 5：进化审计日志（append-only）。

设计借鉴 dsh-self-evolving 的可审计谱系思想（轻量版）：
- 每次插件创建/优化/修复/回滚都必须记一条 entry（hash 链可选，这里用时间戳+序号）
- 日志存于 ~/.drifox/plugins/.evolution/journal.jsonl，append-only
- log 查询支持 action/status/插件名过滤，供 AI 复盘进化历史

操作：log（记录）/ list（查询）/ stats（统计）

> **v0.9.0 起**：日志自动诊断（triage）已迁移到 ``evolution_log_query`` 工具的
> ``triage`` operation，并提供更通用的 list / query / context / triage 四大能力。
"""

import json
import time
from pathlib import Path

from app.tools.result import ToolResult

_ACTIONS = ("create", "optimize", "fix", "rollback", "mcp", "note")


def _plugin_version(plugin_name: str) -> str | None:
    """读取目标插件 manifest 的当前版本（复盘时可看版本变迁；找不到返回 None）"""
    if not plugin_name:
        return None
    roots = []
    try:
        from app.plugins.loaders.plugin_tool_loader import _plugin_roots as _lr

        roots += [Path(p) for p in _lr()]
    except Exception:
        pass
    try:
        from app.utils.utils import get_app_data_dir

        roots.append(Path(get_app_data_dir()) / "plugins")
    except Exception:
        roots.append(Path.home() / ".drifox" / "plugins")
    for r in roots:
        mf = r / plugin_name / ".drifox-plugin" / "plugin.json"
        if mf.exists():
            try:
                return json.loads(mf.read_text(encoding="utf-8")).get("version")
            except json.JSONDecodeError, OSError:
                return None
    return None


def _journal_dir(tool_ctx) -> Path:
    """日志目录：跟 user 插件根同级，避免被当成插件"""
    env = tool_ctx.get("env") or {}
    app_data = env.get("app_data_dir")
    if app_data:
        d = Path(app_data) / "plugins" / ".evolution"
    else:
        d = Path.home() / ".drifox" / "plugins" / ".evolution"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _journal_file(tool_ctx) -> Path:
    return _journal_dir(tool_ctx) / "journal.jsonl"


def _read_entries(tool_ctx) -> list:
    f = _journal_file(tool_ctx)
    if not f.exists():
        return []
    entries = []
    for ln in f.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try:
                entries.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    return entries


def _append(tool_ctx, entry: dict) -> None:
    f = _journal_file(tool_ctx)
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _impl(tool_ctx, **kwargs):
    try:
        op = (kwargs.get("operation") or "log").strip()

        if op == "log":
            action = (kwargs.get("action") or "note").strip()
            if action not in _ACTIONS:
                return ToolResult(
                    False,
                    error=f"action 需为 {_ACTIONS} 之一，当前 {action!r}",
                )
            plugin_name = (kwargs.get("plugin_name") or "").strip()
            summary = (kwargs.get("summary") or "").strip()
            status = (kwargs.get("status") or "ok").strip()
            if not summary:
                return ToolResult(False, error="log 需要 summary（一句话描述本次进化动作）")

            entries = _read_entries(tool_ctx)
            entry = {
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "seq": len(entries) + 1,
                "action": action,
                "plugin": plugin_name or None,
                "version": _plugin_version(plugin_name),
                "status": status,
                "summary": summary[:500],
            }
            _append(tool_ctx, entry)
            ver_note = f" v{entry['version']}" if entry["version"] else ""
            return ToolResult(
                True,
                content=(
                    f"进化日志已记录（#{entry['seq']}）\n"
                    f"  {entry['ts']} [{action}] {plugin_name or '-'}{ver_note} → {status}\n"
                    f"  {summary}"
                ),
            )

        if op == "list":
            entries = _read_entries(tool_ctx)
            f_action = (kwargs.get("action") or "").strip()
            f_plugin = (kwargs.get("plugin_name") or "").strip()
            f_status = (kwargs.get("status") or "").strip()
            filtered = [
                e
                for e in entries
                if (not f_action or e.get("action") == f_action)
                and (not f_plugin or e.get("plugin") == f_plugin)
                and (not f_status or e.get("status") == f_status)
            ]
            if not filtered:
                return ToolResult(True, content="（无匹配的进化日志）")
            raw_limit = kwargs.get("limit")
            if raw_limit is None or raw_limit == "":
                limit = 50
            else:
                try:
                    limit = int(raw_limit)
                except TypeError, ValueError:
                    limit = 50
                if limit < 0:
                    limit = 0
            shown = filtered[-limit:] if limit > 0 else filtered
            lines = [f"进化日志（共 {len(entries)} 条，匹配 {len(filtered)} 条，显示 {len(shown)} 条）：", ""]
            for e in reversed(shown):
                ver = f" v{e['version']}" if e.get("version") else ""
                lines.append(
                    f"#{e.get('seq', '?')} {e.get('ts', '?')} [{e.get('action', '?')}] "
                    f"{e.get('plugin') or '-'}{ver} → {e.get('status', '?')}\n    {e.get('summary', '')}"
                )
            return ToolResult(True, content="\n".join(lines))

        if op == "stats":
            entries = _read_entries(tool_ctx)
            if not entries:
                return ToolResult(True, content="（暂无进化日志，用 operation=log 记录第一条）")
            by_action: dict = {}
            by_plugin: dict = {}
            for e in entries:
                by_action[e.get("action", "?")] = by_action.get(e.get("action", "?"), 0) + 1
                p = e.get("plugin") or "-"
                by_plugin[p] = by_plugin.get(p, 0) + 1
            lines = [f"进化统计（共 {len(entries)} 条）：", ""]
            lines.append("按动作：")
            for a, n in sorted(by_action.items(), key=lambda x: -x[1]):
                lines.append(f"  {a}: {n}")
            lines.append("按插件（top 10）：")
            for p, n in sorted(by_plugin.items(), key=lambda x: -x[1])[:10]:
                lines.append(f"  {p}: {n}")
            return ToolResult(True, content="\n".join(lines))

        return ToolResult(
            False,
            error=(
                f"operation={op!r} 不可用；evolution_journal 当前支持 log/list/stats。"
                " 日志诊断（triage）已迁移到 evolution_log_query.operation=triage"
            ),
        )
    except Exception as e:  # noqa: BLE001
        return ToolResult(False, error=f"evolution_journal 内部异常：{type(e).__name__}: {e}")


_SCHEMA = {
    "type": "function",
    "function": {
        "name": "evolution_journal",
        "description": (
            "自进化：记录/查询进化审计日志（append-only）。"
            "每次插件创建(create)/优化(optimize)/修复(fix)/回滚(rollback)/MCP接入(mcp)"
            "后都应记一条；list 按条件查询历史，stats 看统计。"
            "（v0.9.0 起：日志自动诊断 triage 已迁移到 evolution_log_query）"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["log", "list", "stats"],
                    "description": "log=记录 / list=查询 / stats=统计，默认 log（日志排障用 evolution_log_query）",
                },
                "action": {
                    "type": "string",
                    "enum": list(_ACTIONS),
                    "description": "进化动作类型（log 时必填语义）",
                },
                "plugin_name": {
                    "type": "string",
                    "description": "涉及的插件名",
                },
                "summary": {
                    "type": "string",
                    "description": "一句话描述本次动作（log 必填）",
                },
                "status": {
                    "type": "string",
                    "description": "结果状态：ok/failed/pending，默认 ok",
                },
                "limit": {
                    "type": "integer",
                    "description": "list 显示最近 N 条（默认 50；0=全部），仅 list 生效",
                },
            },
            "required": [],
        },
    },
}


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "evolution_journal",
        _SCHEMA,
        impl=_impl,
        danger="safe",
        icon="evolution_journal",
        cn_name="进化审计日志",
        group="自进化",
        description="记录/查询插件进化审计日志（append-only 可追溯）",
    )
