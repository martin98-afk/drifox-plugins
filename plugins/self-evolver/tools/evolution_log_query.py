# -*- coding: utf-8 -*-
"""evolution_log_query — DriFox 系统日志统一查询工具。

面向大模型排查自己的问题：四大 operation 覆盖排查全场景，避免一次返回
数千行日志爆 context。

- list:    列出 logs/ 下所有可用日志文件 + 大小 + 最后修改时间
- query:   通用查询（核心入口）：按 subsystem/level/since/until/pattern 过滤，
           默认返回摘要（前 N + 后 N + 级别分布）
- context: 取某行前后 N 行深入排查；line_no 是「距文件末尾的行数」（1=最后一行）
- triage:  自动诊断报告：扫 all.log ERROR + 检测工具调用 LOOP + 关联 journal

替代 evolution_journal.operation=triage（已废弃）。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from app.tools.result import ToolResult

# 日志行格式：YYYY-MM-DD HH:MM:SS | LEVEL | [来源] 消息
_LINE_RE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (?P<level>[A-Z]+) \| (?P<rest>.*)$")
_ERROR_RE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (?P<lv>ERROR|CRITICAL) \| (?P<msg>.{0,600})")
_TOOL_LOOP_RE = re.compile(r"Executing tool: ([a-zA-Z_][\w.]*)")
_VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_DEFAULT_SUBSYSTEMS = ("all", "mem_diag")


def _subsystems() -> tuple[str, ...]:
    """从 LOG_ROUTES 派生合法子系统清单（懒加载，避开循环 import）。"""
    try:
        from app.core.logging_setup import LOG_ROUTES

        subs = list(_DEFAULT_SUBSYSTEMS)
        for file_name, _inc, _exc in LOG_ROUTES:
            subs.append(file_name[: -len(".log")])
        return tuple(subs)
    except Exception:
        return _DEFAULT_SUBSYSTEMS


def _logs_dir() -> Path:
    """日志目录：appdata 优先，回退用户根 ~/.drifox/logs。"""
    try:
        from app.utils.utils import get_app_data_dir

        return Path(get_app_data_dir()) / "logs"
    except Exception:
        return Path.home() / ".drifox" / "logs"


def _format_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


def _parse_ts(s: str | None) -> datetime | None:
    """解析 ISO 时间戳 ``2026-08-28 10:14:32``；失败返回 None。"""
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _read_tail(path: Path, lines: int = 20000, approx_bytes: int = 2 * 1024 * 1024) -> list[str]:
    """读文件尾部（GBK 容错）。约读 ``approx_bytes`` 字节，按 ``lines`` 行截断。"""
    if not path.exists():
        return []
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - approx_bytes))
            raw = fh.read()
        return raw.decode("gbk", errors="replace").splitlines()[-lines:]
    except OSError:
        return []


def _list_logs() -> str:
    """列出 logs/ 下所有 .log 文件 + 大小 + 最后修改时间。"""
    log_dir = _logs_dir()
    if not log_dir.exists():
        return f"日志目录不存在: {log_dir}"

    rows: list[tuple[str, int, str]] = []
    for p in sorted(log_dir.glob("*.log")):
        stat = p.stat()
        rows.append(
            (
                p.name,
                stat.st_size,
                datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            )
        )

    if not rows:
        return f"日志目录 {log_dir} 无 .log 文件"

    out = [
        f"日志目录: {log_dir}",
        "",
        f"{'文件名':<25} {'大小':>10}  {'最后修改':<20}",
        "-" * 60,
    ]
    for name, size, mtime in rows:
        out.append(f"{name:<25} {_format_size(size):>10}  {mtime:<20}")
    return "\n".join(out)


def _query(
    subsystem: str | None,
    level: str | None,
    since: str | None,
    until: str | None,
    pattern: str | None,
    head: int,
    tail_n: int,
    max_hits: int,
) -> str:
    """通用查询入口。"""
    sub = subsystem or "all"
    if sub not in _subsystems():
        return f"未知 subsystem: {sub!r}；可选: " + ", ".join(_subsystems())

    log_path = _logs_dir() / f"{sub}.log"
    if not log_path.exists():
        return f"日志文件不存在: {log_path}"

    levels: set[str] = set()
    if level:
        for lv in level.split(","):
            lv = lv.strip().upper()
            if lv in _VALID_LEVELS:
                levels.add(lv)
        if not levels:
            return f"level 解析为空；有效值: {', '.join(_VALID_LEVELS)}"

    since_dt = _parse_ts(since)
    until_dt = _parse_ts(until)
    if since and since_dt is None:
        return f"since 解析失败: {since!r}（期望 'YYYY-MM-DD HH:MM:SS'）"
    if until and until_dt is None:
        return f"until 解析失败: {until!r}（期望 'YYYY-MM-DD HH:MM:SS'）"

    pat: re.Pattern[str] | None = None
    if pattern:
        try:
            pat = re.compile(pattern)
        except re.error as e:
            return f"pattern 编译失败: {e}"

    lines = _read_tail(log_path)
    if not lines:
        return f"[query] subsystem={sub} 文件无内容（{log_path}）"

    hits: list[str] = []
    level_counts: dict[str, int] = {}
    truncated = False
    for ln in lines:
        m = _LINE_RE.match(ln)
        if not m:
            continue
        ts, lv, rest = m.group("ts"), m.group("level"), m.group("rest")
        if levels and lv not in levels:
            continue
        if since_dt or until_dt:
            ln_dt = _parse_ts(ts)
            if ln_dt is None:
                continue
            if since_dt and ln_dt < since_dt:
                continue
            if until_dt and ln_dt > until_dt:
                continue
        if pat and not pat.search(ln):
            continue

        level_counts[lv] = level_counts.get(lv, 0) + 1
        hits.append(f"[{ts}] {lv} | {rest}")
        if len(hits) >= max_hits:
            truncated = True
            break

    if not hits:
        return (
            f"[query] subsystem={sub} level={level or '*'} since={since or '起始'} "
            f"until={until or '当前'} pattern={pattern or '*'} 未命中"
        )

    parts = [
        (
            f"[query] subsystem={sub} level={level or '*'} since={since or '起始'} "
            f"until={until or '当前'} pattern={pattern or '*'}"
        ),
        f"命中 {len(hits)} 条" + ("（已截断至 max_hits）" if truncated else ""),
        f"级别分布: {', '.join(f'{k}={v}' for k, v in sorted(level_counts.items()))}",
        "",
        f"… 前 {min(head, len(hits))} 行 …",
        *hits[:head],
    ]
    if len(hits) > head:
        parts.append("")
        if tail_n > 0:
            if len(hits) > head + tail_n:
                parts.append(f"… 中间省略 {len(hits) - head - tail_n} 行 …")
            parts.append(f"… 后 {min(tail_n, len(hits) - head)} 行 …")
            parts.extend(hits[-tail_n:])

    parts.extend(
        [
            "",
            "提示：用 operation=context line_no=<距末尾行号> n=50 看具体上下文",
        ]
    )
    return "\n".join(parts)


def _context(line_no: int, n: int, subsystem: str | None) -> str:
    """取某行前后 N 行。line_no 是距文件末尾的行数（1=最后一行）。"""
    sub = subsystem or "all"
    if sub not in _subsystems():
        return f"未知 subsystem: {sub!r}；可选: " + ", ".join(_subsystems())

    log_path = _logs_dir() / f"{sub}.log"
    if not log_path.exists():
        return f"日志文件不存在: {log_path}"

    if line_no < 1:
        return f"line_no={line_no} 必须 ≥1（1=最后一行）"

    lines = _read_tail(log_path)
    if not lines:
        return f"{log_path} 无内容"

    total = len(lines)
    idx = total - line_no
    if idx < 0 or idx >= total:
        return f"line_no={line_no} 超出已读范围 1..{total}"

    start = max(0, idx - n)
    end = min(total, idx + n + 1)

    out = [f"[context] subsystem={sub} line_no={line_no}（距末尾）±{n} 行", ""]
    for i in range(start, end):
        marker = " ←" if i == idx else "  "
        out.append(f"{total - i:>6}{marker} {lines[i]}")
    return "\n".join(out)


def _detect_tool_loops(tail: list[str], threshold: int = 8) -> list[tuple[str, int]]:
    """检测 [ToolExecutor] Executing tool 循环：同一工具短窗口连续 ≥threshold 次。"""
    names = [m.group(1) for ln in tail if (m := _TOOL_LOOP_RE.search(ln))]
    alerts: list[tuple[str, int]] = []
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


def _read_journal() -> list[dict]:
    """读 ~/.drifox/plugins/.evolution/journal.jsonl。"""
    try:
        from app.utils.utils import get_app_data_dir

        jf = Path(get_app_data_dir()) / "plugins" / ".evolution" / "journal.jsonl"
    except Exception:
        jf = Path.home() / ".drifox" / "plugins" / ".evolution" / "journal.jsonl"

    if not jf.exists():
        return []
    entries: list[dict] = []
    for ln in jf.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            entries.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return entries


def _triage(lines: int, plugin_filter: str | None) -> str:
    """自动诊断报告：扫 all.log ERROR + 检测 LOOP + 关联 journal 最近动作。"""
    log_path = _logs_dir() / "all.log"
    if not log_path.exists():
        return f"未找到系统日志 {log_path}"

    tail = _read_tail(log_path, lines=lines, approx_bytes=lines * 512)
    if not tail:
        return f"{log_path} 无内容"

    errors = [m.groupdict() for ln in tail if (m := _ERROR_RE.match(ln))]

    known: set[str] = set()
    roots: list[Path] = []
    try:
        from app.plugins.loaders.plugin_tool_loader import _plugin_roots as _lr

        roots.extend(Path(p) for p in _lr())
    except Exception:
        pass
    roots.append(Path.home() / ".drifox" / "plugins")
    for r in roots:
        p = Path(r)
        if p.is_dir():
            known.update(d.name for d in p.iterdir() if d.is_dir())

    mentioned = {n for n in known if n in "\n".join(tail[-200:])}
    if plugin_filter:
        mentioned = {n for n in mentioned if n == plugin_filter}

    out = [f"自进化诊断报告（扫 all.log 尾部 {lines} 行）：", ""]

    loops = _detect_tool_loops(tail)
    if loops:
        out.append(f"⚠⚠ 工具调用循环检测：{len(loops)} 处")
        for name, run in loops:
            out.append(f"  🔁 {name} 连续调用 {run} 次 —— 疑似 AI 行为循环，立即停手！")
        out.append("  处置：停止该工具调用；连续≥3次雷同即应停下等用户裁决")
        out.append("")

    out.append(f"ERROR/CRITICAL：{len(errors)} 条")
    for e in errors[:15]:
        out.append(f"  {e['ts']} [{e['lv']}] {e['msg'].strip()[:180]}")
    if len(errors) > 15:
        out.append(f"  …另 {len(errors) - 15} 条省略")
    if not errors:
        out.append("  （无 ERROR —— 若仍异常，用 query operation 深入查 WARNING 或关键词）")

    out.append("")
    out.append(f"尾部日志提及的已装插件（{len(mentioned)}）：{', '.join(sorted(mentioned)) or '（无）'}")

    entries = _read_journal()
    related = [e for e in entries if e.get("plugin") in mentioned] if mentioned else entries[-5:]
    out.append("")
    out.append("相关插件的最近进化动作（时间线回溯）：")
    if related:
        for e in related[-8:]:
            ver = f" v{e['version']}" if e.get("version") else ""
            out.append(
                f"  #{e.get('seq', '?')} {e.get('ts', '?')} [{e.get('action', '?')}] "
                f"{e.get('plugin') or '-'}{ver} → {e.get('status', '?')}"
            )
            out.append(f"      {e.get('summary', '')}")
    else:
        out.append("  （journal 无相关插件记录 —— 问题可能与自进化动作无关）")

    out.append("")
    out.append("建议：")
    out.append("  1. 若错误集中在某子系统：query subsystem=<sub> level=ERROR")
    out.append("  2. 看具体上下文：context line_no=<距末尾行号> n=50")
    out.append("  3. 排障经验详见 self-evolver references/troubleshooting.md")
    return "\n".join(out)


def _impl(tool_ctx, **kwargs):  # noqa: ARG001
    try:
        op = (kwargs.get("operation") or "query").strip()
        if op == "list":
            return ToolResult(True, content=_list_logs())
        if op == "query":
            try:
                head = max(0, int(kwargs.get("head", 3)))
                tail_n = max(0, int(kwargs.get("tail", 10)))
                max_hits = max(1, min(int(kwargs.get("max_hits", 500)), 5000))
            except TypeError, ValueError:
                head, tail_n, max_hits = 3, 10, 500
            return ToolResult(
                True,
                content=_query(
                    subsystem=kwargs.get("subsystem"),
                    level=kwargs.get("level"),
                    since=kwargs.get("since"),
                    until=kwargs.get("until"),
                    pattern=kwargs.get("pattern"),
                    head=head,
                    tail_n=tail_n,
                    max_hits=max_hits,
                ),
            )
        if op == "context":
            try:
                line_no = int(kwargs.get("line_no", 0))
                n = max(1, min(int(kwargs.get("n", 50)), 500))
            except TypeError, ValueError:
                line_no, n = 0, 50
            return ToolResult(
                True,
                content=_context(line_no, n, kwargs.get("subsystem")),
            )
        if op == "triage":
            try:
                lines = int(kwargs.get("lines") or 500)
            except TypeError, ValueError:
                lines = 500
            lines = max(50, min(lines, 5000))
            plugin_filter = (kwargs.get("plugin_name") or "").strip() or None
            return ToolResult(True, content=_triage(lines, plugin_filter))

        return ToolResult(
            False,
            error=f"未知 operation: {op!r}；可用 list/query/context/triage",
        )
    except Exception as e:  # noqa: BLE001
        return ToolResult(False, error=f"evolution_log_query 内部异常：{type(e).__name__}: {e}")


_SCHEMA = {
    "type": "function",
    "function": {
        "name": "evolution_log_query",
        "description": (
            "DriFox 系统日志统一查询工具（面向 AI 排查自己的问题）。"
            "operation=list 列 logs/ 下所有日志文件；"
            "query 按 subsystem/level/since/until/pattern 过滤，"
            "默认返回摘要（前 N + 后 N + 级别分布）避免爆 context；"
            "context 取具体某行前后 N 行深挖；"
            "triage 自动诊断：扫 all.log ERROR + 检测工具调用 LOOP + 关联 journal。"
            "（替代 evolution_journal.operation=triage）"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["list", "query", "context", "triage"],
                    "description": "list=列文件 / query=通用查询 / context=行上下文 / triage=自动诊断",
                },
                "subsystem": {
                    "type": "string",
                    "description": (
                        "子系统：all / mcp / lsp / gateway / tools / plugins / team / store / llm / ui / mem_diag"
                    ),
                },
                "level": {
                    "type": "string",
                    "description": "日志级别（多选用逗号），如 'ERROR,WARNING'",
                },
                "since": {
                    "type": "string",
                    "description": "起始时间，格式 'YYYY-MM-DD HH:MM:SS'",
                },
                "until": {
                    "type": "string",
                    "description": "截止时间，格式 'YYYY-MM-DD HH:MM:SS'",
                },
                "pattern": {
                    "type": "string",
                    "description": "regex 关键词搜索",
                },
                "head": {
                    "type": "integer",
                    "description": "摘要返回前 N 行（默认 3）",
                },
                "tail": {
                    "type": "integer",
                    "description": "摘要返回后 N 行（默认 10）",
                },
                "max_hits": {
                    "type": "integer",
                    "description": "命中数上限（默认 500，防爆 context）",
                },
                "line_no": {
                    "type": "integer",
                    "description": "context 操作：目标行号（距文件末尾，1=最后一行）",
                },
                "n": {
                    "type": "integer",
                    "description": "context 操作：前后 N 行（默认 50）",
                },
                "lines": {
                    "type": "integer",
                    "description": "triage 操作：扫日志尾部行数（默认 500，上限 5000）",
                },
                "plugin_name": {
                    "type": "string",
                    "description": "triage 操作：限定只关联该插件的 journal 动作",
                },
            },
            "required": [],
        },
    },
}


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "evolution_log_query",
        _SCHEMA,
        impl=_impl,
        danger="safe",
        icon="evolution_log_query",
        cn_name="日志查询",
        group="自进化",
        description="按子系统/级别/时间/关键词查询 DriFox 系统日志，给 AI 排查自己的问题用",
    )
