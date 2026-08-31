# -*- coding: utf-8 -*-
"""
sessions — DriFox 会话检索工具（只读）

查询 <app_data>/sessions.db 的 sessions 表，供写日记、总结、回忆往昔时取材：
- list:   最近会话列表（按更新时间倒序，可按天数/项目过滤）
- search: 关键词全文搜索（title/preview 粗筛 + 解压 messages 细搜，带命中片段）
- read:   读取指定会话的对话内容（可按角色过滤、限制篇幅）

messages 存储格式与主程序 app/core/store/serde.py 一致：
- ZSTD\\x01 + zstd frame（orjson/标准 JSON）
- JSON\\x01 + 原始 JSON（预留格式）
- 无魔数 → 旧版裸 JSON
"""
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from app.tools.result import ToolResult

ROLES = ("user", "assistant")
_title_cache: dict = {}


# ── 数据库定位 ────────────────────────────────────────────

def _db_path(tool_ctx) -> Path:
    app_data = (tool_ctx or {}).get("env", {}).get("app_data_dir")
    if app_data:
        p = Path(app_data) / "sessions.db"
        if p.exists():
            return p
    return Path.home() / ".drifox" / "sessions.db"


def _connect(tool_ctx):
    p = _db_path(tool_ctx)
    if not p.exists():
        return None, f"未找到会话库：{p}"
    try:
        conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=3)
        conn.row_factory = sqlite3.Row
        return conn, None
    except sqlite3.Error as e:
        return None, f"无法打开会话库（只读）：{e}"


# ── messages 反序列化（对齐主程序 serde.py）──────────────

_MAGIC_ZSTD = b"ZSTD"
_MAGIC_JSON = b"JSON"
_VERSION_V1 = b"\x01"


def _deserialize_messages(data) -> list | None:
    if data is None:
        return None
    if isinstance(data, str):
        data = data.encode("utf-8")
    if not data:
        return None
    try:
        if data.startswith(_MAGIC_ZSTD):
            if data[4:5] != _VERSION_V1:
                return None
            from compression import zstd  # PEP 784, Python 3.14+

            return json.loads(zstd.ZstdDecompressor().decompress(data[5:]))
        if data.startswith(_MAGIC_JSON):
            if data[4:5] != _VERSION_V1:
                return None
            return json.loads(data[5:])
        return json.loads(data)
    except Exception:
        return None


def _content_text(msg: dict) -> str:
    """提取消息纯文本；content 为分片列表时拼接 text 部分。"""
    c = msg.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts = []
        for seg in c:
            if isinstance(seg, dict):
                if seg.get("type") == "text" and isinstance(seg.get("text"), str):
                    parts.append(seg["text"])
                elif isinstance(seg.get("text"), str):
                    parts.append(seg["text"])
            elif isinstance(seg, str):
                parts.append(seg)
        return "\n".join(parts)
    if c is None:
        return ""
    return str(c)


def _strip_think(text: str) -> str:
    """剥掉 <think>...</think> 推理块，只留正文。"""
    if "<think>" not in text:
        return text
    out, rest = [], text
    while True:
        head, sep, rest = rest.partition("<think>")
        out.append(head)
        if not sep:
            break
        _, sep2, rest = rest.partition("</think>")
        if not sep2:  # 未闭合：后面的内容全部视为推理，丢弃
            break
    return "".join(out)


def _clean_messages(raw: list | None) -> list:
    """只留 user/assistant 文本轮次，跳过 <system-reminder> 注入块与空消息。"""
    out = []
    if not isinstance(raw, list):
        return out
    for m in raw:
        if not isinstance(m, dict) or m.get("role") not in ROLES:
            continue
        text = _strip_think(_content_text(m)).strip()
        if not text or "<system-reminder>" in text[:200]:
            continue
        out.append({"role": m["role"], "text": text, "ts": str(m.get("timestamp") or "")})
    return out


def _fetch_clean(conn, where: str, params: tuple, order_desc: bool = True):
    """取会话行并解压清洗 messages，返回 (row_dict, clean_msgs) 列表。"""
    sql = (
        "SELECT session_id, title, project, message_count, created_at, updated_at, preview, messages "
        f"FROM sessions {where} ORDER BY updated_at {'DESC' if order_desc else 'ASC'}"
    )
    out = []
    for row in conn.execute(sql, params):
        d = dict(row)
        d["msgs"] = _clean_messages(_deserialize_messages(d.pop("messages")))
        out.append(d)
    return out


# ── 格式化 ────────────────────────────────────────────────

def _fmt_ts(ts: str) -> str:
    return (ts or "")[:16]


def _session_header(d: dict) -> str:
    return (
        f"「{d['title'] or '(无标题)'}」 project={d['project']} "
        f"更新={_fmt_ts(d['updated_at'])} 轮次={d['message_count']} id={d['session_id']}"
    )


def _clip(text: str, pos: int, width: int = 80) -> str:
    """取关键词命中处的上下文片段。"""
    start = max(0, pos - width // 2)
    end = min(len(text), pos + width)
    frag = text[start:end].replace("\n", " ")
    return ("…" if start > 0 else "") + frag + ("…" if end < len(text) else "")


def _days_cutoff(days: int) -> str:
    dt = datetime.now() - timedelta(days=days)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ── 三个 action ──────────────────────────────────────────

def _list_impl(conn, kwargs: dict) -> ToolResult:
    days = _to_int(kwargs.get("days"), 7)
    limit = min(_to_int(kwargs.get("limit"), 20), 50)
    project = str(kwargs.get("project") or "").strip()

    where, params = [], []
    if days > 0:
        where.append("updated_at >= ?")
        params.append(_days_cutoff(days))
    if project:
        where.append("project LIKE ?")
        params.append(f"%{project}%")
    clause = ("WHERE " + " AND ".join(where)) if where else ""

    rows = _fetch_clean(conn, clause, tuple(params))
    if not rows:
        return ToolResult(False, error="该范围内没有会话")

    lines = []
    for d in rows[:limit]:
        first_user = next((m["text"][:60] for m in d["msgs"] if m["role"] == "user"), "")
        lines.append(
            f"[{_fmt_ts(d['updated_at'])}] {d['title'] or '(无标题)'}"
            f"（{d['project']}，{len(d['msgs'])} 轮）id={d['session_id']}"
            + (f" 开头：{first_user}" if first_user else "")
        )
    total = len(rows)
    header = f"找到 {total} 个会话（显示最近 {min(limit, total)} 个）"
    return ToolResult(True, content=header + "\n" + "\n".join(lines))


def _search_impl(conn, kwargs: dict) -> ToolResult:
    query = str(kwargs.get("query") or "").strip()
    if not query:
        return ToolResult(False, error="query 不能为空")
    days = _to_int(kwargs.get("days"), 30)
    limit = min(_to_int(kwargs.get("limit"), 10), 20)
    project = str(kwargs.get("project") or "").strip()

    where, params = [], []
    if days > 0:
        where.append("updated_at >= ?")
        params.append(_days_cutoff(days))
    if project:
        where.append("project LIKE ?")
        params.append(f"%{project}%")
    clause = ("WHERE " + " AND ".join(where)) if where else ""

    found = []  # (updated_at, session_id, title, project, turns, [片段])
    for d in _fetch_clean(conn, clause, tuple(params)):
        hits = []
        # 元信息命中
        for field in ("title", "preview"):
            v = str(d.get(field) or "")
            pos = v.lower().find(query.lower())
            if pos >= 0:
                hits.append(f"{field}: {_clip(v, pos)}")
        # 消息正文命中
        for m in d["msgs"]:
            pos = m["text"].lower().find(query.lower())
            if pos >= 0:
                hits.append(f"{m['role']}@{_fmt_ts(m['ts'])}: {_clip(m['text'], pos)}")
            if len(hits) >= 3:
                break
        if hits:
            found.append((d["updated_at"], d["session_id"], d["title"], d["project"], len(d["msgs"]), hits[:3]))
        if len(found) >= limit:
            break

    if not found:
        return ToolResult(False, error=f"没搜到「{query}」（范围：{'全部时间' if days == 0 else f'近 {days} 天'}）")

    lines = [f"「{query}」命中 {len(found)} 个会话："]
    for _, sid, title, proj, turns, hits in found:
        lines.append("")
        lines.append(_session_header({"session_id": sid, "title": title, "project": proj,
                                      "updated_at": _, "message_count": turns}))
        for h in hits:
            lines.append(f"  · {h}")
    lines.append("")
    lines.append("想看哪段完整对话，用 sessions read + 对应 id。")
    return ToolResult(True, content="\n".join(lines))


def _read_impl(conn, kwargs: dict) -> ToolResult:
    sid = str(kwargs.get("session_id") or "").strip()
    if not sid:
        return ToolResult(False, error="session_id 不能为空（可从 sessions list/search 结果里拿）")
    role = str(kwargs.get("role") or "all").lower()
    if role not in ("all", *ROLES):
        return ToolResult(False, error=f"role 须为 all/{'/'.join(ROLES)}")
    max_msgs = min(_to_int(kwargs.get("max_messages"), 200), 500)
    max_chars = min(_to_int(kwargs.get("max_chars"), 20000), 60000)

    rows = _fetch_clean(conn, "WHERE session_id = ?", (sid,))
    if not rows:
        rows = _fetch_clean(conn, "WHERE session_id LIKE ?", (sid + "%",))
    if not rows:
        return ToolResult(False, error=f"没有找到会话 {sid}")
    d = rows[0]
    msgs = [m for m in d["msgs"] if role == "all" or m["role"] == role]
    if not msgs:
        return ToolResult(False, error=f"会话 {d['session_id']} 内没有符合条件的消息")

    lines = [
        f"「{d['title'] or '(无标题)'}」 project={d['project']} 共 {len(msgs)} 轮（截取前 {max_msgs} 轮 / {max_chars} 字）",
    ]
    used = 0
    for m in msgs[:max_msgs]:
        text = m["text"]
        if len(text) > 3000:
            text = text[:3000] + f"…（该轮过长，剩 {len(text) - 3000} 字）"
        ts = _fmt_ts(m["ts"])[11:] or "--:--"
        line = f"[{ts}] {m['role']}: {text}"
        if used + len(line) > max_chars:
            lines.append(f"…（已达 {max_chars} 字上限，后面还有 {len(msgs) - msgs.index(m)} 轮未展示）")
            break
        lines.append(line)
        used += len(line)
    return ToolResult(True, content="\n\n".join(lines))


def _to_int(v, default: int) -> int:
    try:
        n = int(v)
        return n if n >= 0 else default
    except (TypeError, ValueError):
        return default


# ── 注册 ─────────────────────────────────────────────────

_SCHEMA = {
    "type": "function",
    "function": {
        "name": "sessions",
        "description": (
            "DriFox 会话检索（只读）。写日记、总结、回忆之前聊过的内容时用它取材。"
            "action=list：最近会话列表；action=search：关键词全文搜索（返回命中片段）；"
            "action=read：按 session_id 读取某次对话的完整内容。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "search", "read"],
                    "description": "list=最近会话；search=关键词搜索；read=读指定会话",
                },
                "query": {
                    "type": "string",
                    "description": "search 必填：关键词（不区分大小写）",
                },
                "session_id": {
                    "type": "string",
                    "description": "read 必填：会话 id（支持前缀）",
                },
                "days": {
                    "type": "integer",
                    "description": "回看最近 N 天（list 默认 7，search 默认 30；0=不限）",
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回几条（list 默认 20，search 默认 10）",
                },
                "project": {
                    "type": "string",
                    "description": "按项目名模糊过滤（可选）",
                },
                "role": {
                    "type": "string",
                    "enum": ["all", "user", "assistant"],
                    "description": "read 时按角色过滤（默认 all）",
                },
                "max_messages": {
                    "type": "integer",
                    "description": "read 最多读几轮（默认 200）",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "read 最多返回多少字（默认 20000）",
                },
            },
            "required": ["action"],
        },
    },
}


def _session_title(session_id: str) -> str:
    """按 id/前缀查会话标题，供 preview 显示；失败返回空串。"""
    sid = (session_id or "").strip()
    if not sid:
        return ""
    cached = _title_cache.get(sid)
    if cached is not None:
        return cached
    title = ""
    p = _db_path({})
    try:
        if p.exists():
            conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=3)
            try:
                row = conn.execute(
                    "SELECT title FROM sessions WHERE session_id = ?", (sid,)
                ).fetchone()
                if row is None:
                    row = conn.execute(
                        "SELECT title FROM sessions WHERE session_id LIKE ? LIMIT 1",
                        (sid + "%",),
                    ).fetchone()
                title = str(row[0] or "") if row else ""
            finally:
                conn.close()
    except Exception:
        title = ""
    if len(_title_cache) > 64:
        _title_cache.clear()
    _title_cache[sid] = title
    return title


def _preview(args: dict) -> str:
    action = (args or {}).get("action", "")
    if action == "search":
        return f"搜索会话「{str((args or {}).get('query', ''))[:30]}」"
    if action == "read":
        sid = str((args or {}).get("session_id", ""))
        title = _session_title(sid)
        if title:
            return f"读取会话「{title[:30]}」"
        return f"读取会话 {sid[:16]}"
    days = (args or {}).get("days")
    return f"最近会话（{days}天）" if days else "最近会话"


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    from app.tools.registry import make_summarize_from_preview

    def _dispatch(tool_ctx, **kw):
        conn, err = _connect(tool_ctx)
        if conn is None:
            return ToolResult(False, error=err or "无法打开会话库")
        try:
            action = kw.get("action")
            if action == "list":
                return _list_impl(conn, kw)
            if action == "search":
                return _search_impl(conn, kw)
            if action == "read":
                return _read_impl(conn, kw)
            return ToolResult(False, error=f"未知 action：{action}")
        finally:
            conn.close()

    registry.register(
        "sessions",
        _SCHEMA,
        impl=_dispatch,
        danger="safe",
        icon="sessions",
        cn_name="会话检索",
        group="openhanako",
        description="DriFox 会话库检索（最近列表/关键词搜索/读取内容）",
        aliases=["会话", "检索会话"],
        render_mode="",
        preview=_preview,
        summarize=make_summarize_from_preview(_preview),
    )
