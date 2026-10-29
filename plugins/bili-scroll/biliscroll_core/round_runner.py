# -*- coding: utf-8 -*-
"""值班轮驱动：组装章程 + 设置 + 工具集，经引擎会话跑一轮。

工具执行说明：turn(tools=...) 只决定模型「看得见」哪些工具；实际调用由
worker 的 ToolExecutor 路由到 tools/bili_tools.py 注册的 impl（vendor
server 的工具函数在宿主进程内直接执行）。
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Dict, List

from loguru import logger

from .paths import PLUGIN_ROOT
from .store import DutyStore

PLUGIN_NAME = "bili-scroll"
SKILL_PATH = PLUGIN_ROOT / "skills" / "bili-scroll-duty" / "SKILL.md"
ROUND_TIMEOUT_SECONDS = 20 * 60

# 值班轮可见的 B站工具名（tools/bili_tools.py 注册的子集；写类需配置开启）
BASE_TOOLS = [
    "bili_recommend", "bili_search", "bili_subtitle", "bili_video_info",
    "bili_comments", "bili_danmaku", "bili_cover", "bili_frames",
    "bili_user_info",
]
COMMENT_TOOLS = ["bili_reply"]            # auto_comment 开才给
REPLY_TOOLS = ["bili_received_replies"]   # reply_comments 开才给

# 本地窄口工具 schema（与 tools/bili_duty_data.py 的注册保持一致）
LOCAL_TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {"type": "function", "function": {
        "name": "bili_report_append",
        "description": "向今天的日报追加一段文本（值班轮专用，路径固定不可传）",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string", "description": "要追加的 Markdown 文本"}},
            "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "bili_seen_append",
        "description": "向判重表记一行（status: 挑了/跳过/评论；发过评论必须带 rpid）",
        "parameters": {"type": "object", "properties": {
            "bvid": {"type": "string"}, "title": {"type": "string"},
            "up": {"type": "string"}, "status": {"type": "string",
            "enum": ["挑了", "跳过", "评论"]},
            "rpid": {"type": "string", "description": "评论 rpid，从 bili_reply 返回取，没取到就留空"},
            "root": {"type": "string", "description": "回复楼中楼时填根评论 rpid"}},
            "required": ["bvid", "title", "up", "status"]}}},
    {"type": "function", "function": {
        "name": "bili_seen_recent",
        "description": "查判重表最近记录（新→旧），用于去重与找回自己发过的评论",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "number", "description": "默认 40"},
            "bvid": {"type": "string", "description": "只查某条"}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "bili_digest_append",
        "description": "向本月归档追加一行（看过的每条都要记，跳过的注明理由）",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string"}}, "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "bili_paths",
        "description": "查看日报/判重表/归档的实际路径",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
]


def load_settings() -> Dict[str, Any]:
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    values = PluginConfigStore().get_all(PLUGIN_NAME)
    # 数字字段归一化（config store 对 number 存 str）
    for key in ("daily_quota", "comment_quota"):
        try:
            values[key] = int(float(values.get(key) or 0))
        except (TypeError, ValueError):
            values[key] = 0
    for key in ("peak_noon", "peak_night", "auto_comment", "reply_comments"):
        values[key] = str(values.get(key)).lower() in ("1", "true", "yes", "on")
    values["report_mode"] = values.get("report_mode") or "full"
    return values


def _collect_tool_schemas(settings: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 schema_registry 取值班轮可见的 schema（bili_tools 注册时填充）。"""
    from biliscroll_core.schema_registry import TOOL_SCHEMAS

    allowed = set(BASE_TOOLS)
    if settings.get("auto_comment"):
        allowed |= set(COMMENT_TOOLS)
    if settings.get("reply_comments"):
        allowed |= set(REPLY_TOOLS)

    out: List[Dict[str, Any]] = []
    missing: List[str] = []
    for name in sorted(allowed):
        schema = TOOL_SCHEMAS.get(name)
        if schema is None:
            missing.append(name)
            continue
        out.append(schema)
    if missing:
        logger.warning(f"[bili-scroll] 值班轮缺工具 schema（未注册）：{', '.join(missing)}")
    return out


def _opening_user_message(store: DutyStore, settings: Dict[str, Any]) -> str:
    """开场指令：设置快照 + 今日状态。章程在 system，这里只给本轮事实。"""
    picked = store.count_picked_today()
    quota = int(settings.get("daily_quota") or 0)
    keywords = (settings.get("keywords") or "").strip()
    lines = [
        f"今天是 {_dt.date.today().isoformat()}，开始这一轮值班。",
        f"- 关键词：{'已设置，逐行用 bili_search 搜（近 7 天优先）' if keywords else '未设置，用 bili_recommend 刷首页推荐流，随机挑，别固定取前 N'}",
        f"- 今天已挑 {picked} 条，配额 {quota} 条" + ("（已满，本轮只补归档与判重）" if quota and picked >= quota else ""),
        f"- 日报档位：{settings.get('report_mode')}（完整 full / 薄版 thin / 不写 none，判重表任何档位都要写）",
        f"- 日报路径：{store.report_path()}（一天一份，追加别覆盖；每段以 ### BV号 开头）",
        f"- 判重表：{store.seen_path}（动手前先 bili_seen_recent 查重）",
        f"- 归档：{store.digest_path()}（看过的每条都记，含跳过理由）",
    ]
    if settings.get("auto_comment"):
        uid = (settings.get("my_uid") or "").strip()
        per_round = min(int(settings.get("comment_quota") or 1), 20)
        delivery = settings.get("delivery") or "comment"
        delivery_desc = {"comment": "只发公开评论", "dm_only": "只发私信（bili_send_message，一条公开评论都不发）",
                         "both": "公开评论照发，另加一条私信"}.get(delivery, "只发公开评论")
        lines += [
            f"- 自动评论：开着。投递方式：{delivery_desc}。每轮最多 {per_round} 条，@ UID {uid or '（未填，发不了 @，只写报告）'}",
            "- bili_reply 返回 blocked_by 时按提示改写一次，再被拦就不发并记入报告；"
            "私信上限 500 字符（code 21007 被拒就精简一次重发，一轮只发一条）",
        ]
    else:
        lines.append("- 自动评论：关着。本轮只看不发，bili_reply 不可用也不许尝试")
    if settings.get("reply_comments"):
        lines.append("- 回复评论：开着。先 bili_seen_recent 查最近 7 天自己发过的评论（带 rpid），只回直接回复到那条下面的，每条 ≤100 字")
    persona = (settings.get("persona") or "").strip()
    if persona:
        lines.append(f"- 使用者人设补充：{persona}")
    lines.append("转写：v1 未启用本地转写；没字幕的视频先按「演示类看画面」判断一次，看过仍说不清才跳过，"
                 "并在报告末尾写「因无字幕跳过 N 条」。")
    lines.append("保底：报告至少一行（「不写日报」档除外）、判重表至少一行，先把这两样落下再干别的。")
    return "\n".join(lines)


def run_duty_round() -> Dict[str, Any]:
    """同步跑一轮（调用方负责放线程）。返回 {status, text, error, report_path}。

    模块级互斥：工具入口（bili_duty_run）与 UI 按钮（卡片）共用本函数，
    同一时刻只允许一轮；拿不到锁返回 status=busy。
    """
    import threading

    from app.plugins.capabilities.resolve import pool_for

    if not _ROUND_LOCK.acquire(blocking=False):
        return {"status": "busy", "error": "已有一轮值班在跑", "text": ""}
    try:
        return _run_duty_round_locked()
    finally:
        _ROUND_LOCK.release()


_ROUND_LOCK = threading.Lock()


def _run_duty_round_locked() -> Dict[str, Any]:
    settings = load_settings()
    store = DutyStore()

    tools = _collect_tool_schemas(settings)
    if not tools:
        return {"status": "error", "error": "没取到任何 B站工具 schema（插件工具未注册成功）", "text": ""}

    pool_ui = pool_for(plugin=PLUGIN_NAME, surface="ui") or {}
    create_session = pool_ui.get("engine.session")
    if not callable(create_session):
        return {"status": "error", "error": "engine.session 能力不可用（未声明或无窗口）", "text": ""}

    charter = SKILL_PATH.read_text(encoding="utf-8") if SKILL_PATH.is_file() else ""
    if not charter:
        return {"status": "error", "error": f"值班章程缺失：{SKILL_PATH}", "text": ""}

    session = create_session(PLUGIN_NAME)
    result = session.turn(
        system=charter,
        user=_opening_user_message(store, settings),
        tools=tools + LOCAL_TOOL_SCHEMAS,
        timeout=ROUND_TIMEOUT_SECONDS,
    )
    err = getattr(result, "error", None)
    status = "error" if err else ("cancelled" if getattr(result, "cancelled", False)
                                  else ("timeout" if getattr(result, "timed_out", False) else "success"))
    return {
        "status": status,
        "error": str(err or ""),
        "text": str(getattr(result, "text", "") or ""),
        "report_path": str(store.report_path()),
    }
