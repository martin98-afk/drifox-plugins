# -*- coding: utf-8 -*-
"""
evolution_journal — 自进化工具 5：进化审计日志（append-only）。

设计借鉴 dsh-self-evolving 的可审计谱系思想（轻量版）：
- 每次插件创建/优化/修复/回滚都必须记一条 entry（hash 链可选，这里用时间戳+序号）
- 日志存于 ~/.drifox/plugins/.evolution/journal.jsonl，append-only
- log 查询支持 action/status/插件名过滤，供 AI 复盘进化历史

操作：log（记录）/ list（查询）/ stats（统计）
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
            except (json.JSONDecodeError, OSError):
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


def _system_log_tail(lines: int = 500) -> list:
    """读系统日志尾部 N 行（GBK 编码容错；文件可能数 MB，只读尾部）"""
    f = Path.home() / ".drifox" / "logs" / "llm_chatter.log"
    if not f.exists():
        return []
    try:
        with open(f, "rb") as fh:
            fh.seek(0, 2)  # 末尾
            size = fh.tell()
            fh.seek(max(0, size - lines * 512))  # 每行上限约 512B，粗略定位
            raw = fh.read()
        return raw.decode("gbk", errors="replace").splitlines()[-lines:]
    except OSError:
        return []


_LOG_RE = None


def _detect_tool_loops(tail: list, window: int = 8, threshold: int = 8) -> list:
    """检测工具调用循环（2026-08-22 #31-#62 事故补强）

    扫 [ToolExecutor] Executing tool: <name> 轨迹：同一工具名连续出现
    >=threshold 次即报警。事故场景：32 条 evolution_journal note 全是
    INFO 级成功记录，ERROR 扫描完全盲区。
    """
    import re

    tool_re = re.compile(r"Executing tool: ([a-zA-Z_][\w.]*)")
    names = [m.group(1) for ln in tail if (m := tool_re.search(ln))]
    alerts = []
    i = 0
    while i < len(names):
        j = i
        while j < len(names) and names[j] == names[i]:
            j += 1
        run = j - i
        if run >= threshold:
            alerts.append((names[i], run))
        i = j
    return alerts


def _triage(lines: int, plugin_filter: str) -> str:
    """扫系统日志尾部 ERROR → 提及的插件 → 关联 journal 最近动作 → 诊断报告"""
    import re

    tail = _system_log_tail(lines)
    if not tail:
        return "未找到系统日志 ~/.drifox/logs/llm_chatter.log（或不可读）"

    err_re = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (ERROR|CRITICAL) \| (.{0,600})")
    errors = [m.groups() for ln in tail if (m := err_re.match(ln))]

    # 从错误行 + 全尾部提取涉及插件名（命中已装插件目录名才算）
    known = set()
    env_roots = []
    try:
        from app.plugins.loaders.plugin_tool_loader import _plugin_roots as _lr

        env_roots += list(_lr())
    except Exception:
        pass
    env_roots.append(Path.home() / ".drifox" / "plugins")
    for r in env_roots:
        p = Path(r)
        if p.is_dir():
            known.update(d.name for d in p.iterdir() if d.is_dir())

    mentioned = {n for n in known if n in "\n".join(tail[-200:])}
    if plugin_filter:
        mentioned = {n for n in mentioned if n == plugin_filter}

    lines_out = [f"自进化诊断报告（扫系统日志尾部 {lines} 行）：", ""]

    # LOOP 检测（先于 ERROR：行为循环比系统报错更隐蔽）
    loops = _detect_tool_loops(tail)
    if loops:
        lines_out.append(f"⚠⚠ 工具调用循环检测：{len(loops)} 处")
        for name, run in loops:
            lines_out.append(f"  🔁 {name} 连续调用 {run} 次 —— 疑似 AI 行为循环，立即停手！")
        lines_out.append("  处置：停止该工具调用；连续≥3次雷同即应停下等用户裁决（见 troubleshooting.md 第五节）")
        lines_out.append("")

    lines_out.append(f"ERROR/CRITICAL：{len(errors)} 条")
    for ts, lv, msg in errors[:15]:
        lines_out.append(f"  {ts} [{lv}] {msg.strip()[:180]}")
    if len(errors) > 15:
        lines_out.append(f"  …另 {len(errors) - 15} 条省略")
    if not errors:
        lines_out.append("  （无 ERROR —— 若仍异常，用 WARNING 级别或 Select-String '<插件名>' 手查）")

    lines_out.append("")
    lines_out.append(f"尾部日志提及的已装插件（{len(mentioned)}）：{', '.join(sorted(mentioned)) or '（无）'}")

    # 关联 journal：提及插件/全部的最近动作
    entries = _read_entries({"env": {}})
    related = [e for e in entries if e.get("plugin") in mentioned] if mentioned else entries[-5:]
    lines_out.append("")
    lines_out.append("相关插件的最近进化动作（时间线回溯）：")
    if related:
        for e in related[-8:]:
            ver = f" v{e['version']}" if e.get("version") else ""
            lines_out.append(f"  #{e.get('seq', '?')} {e.get('ts', '?')} [{e.get('action', '?')}] {e.get('plugin') or '-'}{ver} → {e.get('status', '?')}")
            lines_out.append(f"      {e.get('summary', '')}")
    else:
        lines_out.append("  （journal 无相关插件记录 —— 问题可能与自进化动作无关）")

    lines_out.append("")
    lines_out.append("建议：")
    lines_out.append("  1. 若错误集中在某插件：先看该插件最近一次 journal 动作改了什么，再针对性回滚/修复")
    lines_out.append("  2. 手查更多：Get-Content ~/.drifox/logs/llm_chatter.log -Tail 500 | Select-String 'ERROR|<插件名>'")
    lines_out.append("  3. 排障经验详见 self-evolver references/troubleshooting.md")
    return "\n".join(lines_out)


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
                e for e in entries
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
                except (TypeError, ValueError):
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

        if op == "triage":
            try:
                lines = int(kwargs.get("lines") or 500)
            except (TypeError, ValueError):
                lines = 500
            lines = max(50, min(lines, 5000))
            return ToolResult(True, content=_triage(lines, (kwargs.get("plugin_name") or "").strip()))

        return ToolResult(False, error=f"未知 operation: {op!r}；可用 log/list/stats/triage")
    except Exception as e:  # noqa: BLE001
        return ToolResult(False, error=f"evolution_journal 内部异常：{type(e).__name__}: {e}")


_SCHEMA = {
    "type": "function",
    "function": {
        "name": "evolution_journal",
        "description": (
            "自进化：记录/查询进化审计日志（append-only）。"
            "每次插件创建(create)/优化(optimize)/修复(fix)/回滚(rollback)/MCP接入(mcp)"
            "后都应记一条；list 按条件查询历史，stats 看统计，triage 扫系统日志 ERROR "
            "并关联进化动作自助排障。让进化过程可追溯、可自查。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["log", "list", "stats", "triage"],
                    "description": "log=记录 / list=查询 / stats=统计 / triage=扫系统日志排障，默认 log",
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
                "lines": {
                    "type": "integer",
                    "description": "triage 扫系统日志尾部行数（默认 500，上限 5000）",
                },
            },
            "required": [],
        },
    },
}


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "evolution_journal", _SCHEMA, impl=_impl,
        danger="safe", icon="evolution_journal", cn_name="进化审计日志",
        group="自进化", description="记录/查询插件进化审计日志（append-only 可追溯）",
    )
