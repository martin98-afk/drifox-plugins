# -*- coding: utf-8 -*-
"""值班轮窄口写入工具（章程对应的 duty_* 五件套）。

设计约束（对齐 dsh 版「最小权限 profile」语义）：路径全部由插件定死，
不接受任何路径参数；只写 plugin_data/bili-scroll/ 自己的一亩三分地。
工具对全池可见（DriFox 无 per-session 工具白名单），值班轮经 turn(tools=)
选入；普通对话误调也无害——写的只是值班数据目录。
"""
from __future__ import annotations

import json

from app.tools.result import ToolResult

from biliscroll_core.store import DutyStore

_ERROR = ToolResult(False, error="数据目录不可用：能力池未就绪，请重启 DriFox 后重试")


def _store() -> DutyStore | None:
    try:
        return DutyStore()
    except Exception:
        return None


def _report_append_impl(tool_ctx, text: str = "", **_) -> ToolResult:
    store = _store()
    if store is None:
        return _ERROR
    if not (text or "").strip():
        return ToolResult(False, error="text 不能为空（保底契约：报告至少留一行）")
    path = store.report_append(text)
    return ToolResult(True, content=f"已追加日报：{path}")


def _seen_append_impl(tool_ctx, bvid: str = "", title: str = "", up: str = "",
                      status: str = "", rpid: str = "", root: str = "", **_) -> ToolResult:
    store = _store()
    if store is None:
        return _ERROR
    if not (bvid and title and up and status):
        return ToolResult(False, error="bvid/title/up/status 必填")
    if status == "评论" and not (rpid or "").strip():
        # 章程红线：没取到 rpid 要如实记，这里照收但回执提醒，不许编
        store.seen_append(bvid, title, up, status, rpid="", root=root)
        return ToolResult(True, content="已记入判重表（注意：未取到 rpid，已在记录中留空，不得编造）")
    store.seen_append(bvid, title, up, status, rpid=rpid, root=root)
    return ToolResult(True, content="已记入判重表")


def _seen_recent_impl(tool_ctx, limit: int = 40, bvid: str = "", **_) -> ToolResult:
    store = _store()
    if store is None:
        return _ERROR
    rows = store.seen_recent(limit=int(limit or 40), bvid=bvid)
    return ToolResult(True, content=json.dumps(rows, ensure_ascii=False, indent=1))


def _digest_append_impl(tool_ctx, text: str = "", **_) -> ToolResult:
    store = _store()
    if store is None:
        return _ERROR
    if not (text or "").strip():
        return ToolResult(False, error="text 不能为空")
    path = store.digest_append(text)
    return ToolResult(True, content=f"已追加归档：{path}")


def _paths_impl(tool_ctx, **_) -> ToolResult:
    store = _store()
    if store is None:
        return _ERROR
    return ToolResult(True, content=json.dumps({
        "日报": str(store.report_path()),
        "判重表": str(store.seen_path),
        "归档": str(store.digest_path()),
    }, ensure_ascii=False, indent=1))


def register(registry):
    common = dict(danger="safe", icon="bili", group="B站值班")
    registry.register(
        "bili_report_append",
        {"type": "function", "function": {
            "name": "bili_report_append",
            "description": "值班轮专用：向今天的日报追加一段（路径固定）。一天一份追加别覆盖，每段以 ### BV号 开头",
            "parameters": {"type": "object", "properties": {
                "text": {"type": "string"}}, "required": ["text"]}},
        },
        impl=_report_append_impl, cn_name="B站值班·写日报", description="追加值班日报",
        **common)
    registry.register(
        "bili_seen_append",
        {"type": "function", "function": {
            "name": "bili_seen_append",
            "description": "值班轮专用：向判重表记一行（挑了/跳过/评论）。发评论后必须记 rpid，没取到就留空、绝不编造",
            "parameters": {"type": "object", "properties": {
                "bvid": {"type": "string"}, "title": {"type": "string"},
                "up": {"type": "string"},
                "status": {"type": "string", "enum": ["挑了", "跳过", "评论"]},
                "rpid": {"type": "string"}, "root": {"type": "string"}},
                "required": ["bvid", "title", "up", "status"]}},
        },
        impl=_seen_append_impl, cn_name="B站值班·记判重", description="记判重表一行",
        **common)
    registry.register(
        "bili_seen_recent",
        {"type": "function", "function": {
            "name": "bili_seen_recent",
            "description": "值班轮专用：查判重表最近记录（新→旧），去重与找回自己发过的评论",
            "parameters": {"type": "object", "properties": {
                "limit": {"type": "number"}, "bvid": {"type": "string"}},
                "required": []}},
        },
        impl=_seen_recent_impl, cn_name="B站值班·查判重", description="查判重表最近记录",
        **common)
    registry.register(
        "bili_digest_append",
        {"type": "function", "function": {
            "name": "bili_digest_append",
            "description": "值班轮专用：向本月归档追加一行（看过的每条都记，格式：日期 · BV号 · 标题 · UP · 一句话结论 · 链接）",
            "parameters": {"type": "object", "properties": {
                "text": {"type": "string"}}, "required": ["text"]}},
        },
        impl=_digest_append_impl, cn_name="B站值班·记归档", description="追加月度归档",
        **common)
    registry.register(
        "bili_paths",
        {"type": "function", "function": {
            "name": "bili_paths",
            "description": "值班轮专用：查看日报/判重表/归档的实际路径",
            "parameters": {"type": "object", "properties": {}, "required": []}},
        },
        impl=_paths_impl, cn_name="B站值班·看路径", description="查看值班数据路径",
        **common)
