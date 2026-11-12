# -*- coding: utf-8 -*-
"""团队消息轨迹 —— 邮箱聚合、快照落盘与回放。

数据源是宿主 TeamManager 邮箱（team.read 能力）：task/reply 邮件逐封 JSON
落在收件人邮箱目录，事件形状 ``{mail_id, kind, from, to, time, status,
success, subject, body, result}``。邮箱是「在线信箱」语义（成员离队整目录
删除），因此聚合结果按 ``mail_id`` 增量追加到插件数据目录的 jsonl 快照，
团队解散后凭快照回放全程轨迹。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .plugin_config import plugin_data_dir

# 单 run 快照事件上限（对齐 dsh-context 的 bounded 思路）
SNAPSHOT_MAX_EVENTS = 2000


def snapshot_path(team_run_id: str) -> Path:
    safe = "".join(c for c in (team_run_id or "unknown") if c.isalnum() or c in "-_")
    return plugin_data_dir() / "teamcomms" / f"{safe}.jsonl"


def normalize_mail(mail: Dict[str, Any], mailbox_owner_agent: str) -> Optional[Dict[str, Any]]:
    """把宿主邮件 dict 归一成轨迹事件；缺发件人或收件人的丢弃。"""
    kind = mail.get("type")
    if kind not in ("task", "reply"):
        return None
    from_agent = str(mail.get("from_agent") or "").strip()
    to_agent = str(mail.get("to_agent") or mailbox_owner_agent or "").strip()
    if not from_agent or not to_agent:
        return None
    try:
        created = float(mail.get("created_at") or 0)
    except (TypeError, ValueError):
        created = 0.0
    return {
        "mail_id": str(mail.get("id") or f"{created}_{from_agent}_{to_agent}"),
        "kind": kind,
        "from": from_agent,
        "to": to_agent,
        "time": created,
        "status": str(mail.get("status") or ""),
        "success": bool(mail.get("success", True)) if kind == "reply" else None,
        "subject": str(mail.get("subject") or ""),
        "body": str(mail.get("body") or ""),
        "result": str(mail.get("result") or ""),
        "reply_to": str(mail.get("reply_to") or "") if kind == "reply" else "",
    }


def gather_team_comms(team_read: Any, team_name: str) -> Dict[str, Any]:
    """聚合一个团队的成员名单与全部邮箱事件。

    team_read 是 team.read 能力面（只读代理）。任何成员读取失败都降级跳过，
    不让单个邮箱坏文件废掉整图。
    """
    getter = team_read.get if hasattr(team_read, "get") else lambda name: getattr(team_read, name, None)

    def call(name: str, *args: Any) -> Any:
        fn = getter(name)
        return fn(*args) if callable(fn) else None

    members: List[Dict[str, Any]] = []
    try:
        raw = call("get_members", team_name) or []
    except Exception:
        raw = []
    for item in raw:
        if isinstance(item, dict) and item.get("agent_name"):
            members.append(item)

    leader = ""
    try:
        leader_wid = call("get_leader_window_id", team_name) or ""
    except Exception:
        leader_wid = ""
    for member in members:
        if member.get("window_id") and member.get("window_id") == leader_wid:
            leader = str(member.get("agent_name") or "")
            break

    events: List[Dict[str, Any]] = []
    seen_ids = set()
    for member in members:
        owner = str(member.get("agent_name") or "")
        wid = str(member.get("window_id") or "")
        if not wid:
            continue
        try:
            mails = call("get_mailbox_mails", wid, team_name) or []
        except Exception:
            continue
        for mail in mails if isinstance(mails, list) else []:
            if not isinstance(mail, dict):
                continue
            event = normalize_mail(mail, owner)
            if event is None or event["mail_id"] in seen_ids:
                continue
            seen_ids.add(event["mail_id"])
            events.append(event)
    events.sort(key=lambda e: (e["time"], e["mail_id"]))
    if not leader:
        # 回放兜底：leader 未登记时按 task 发送数最多者置顶
        counts: Dict[str, int] = {}
        for event in events:
            if event["kind"] == "task":
                counts[event["from"]] = counts.get(event["from"], 0) + 1
        if counts:
            leader = max(counts, key=lambda name: counts[name])
    return {"members": members, "leader": leader, "events": events}


def append_snapshot(team_run_id: str, events: List[Dict[str, Any]]) -> int:
    """把新事件按 mail_id 增量追加进快照，返回本次追加条数。

    超上限时截断保留最近的 SNAPSHOT_MAX_EVENTS 条。
    """
    if not events:
        return 0
    path = snapshot_path(team_run_id)
    known: Dict[str, Dict[str, Any]] = {}
    if path.exists():
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    old = json.loads(line)
                except Exception:
                    continue
                if isinstance(old, dict) and old.get("mail_id"):
                    known[str(old["mail_id"])] = old
        except Exception:
            known = {}
    fresh = [e for e in events if e.get("mail_id") and str(e["mail_id"]) not in known]
    if not fresh:
        return 0
    merged = list(known.values()) + fresh
    merged.sort(key=lambda e: (float(e.get("time") or 0), str(e.get("mail_id") or "")))
    if len(merged) > SNAPSHOT_MAX_EVENTS:
        merged = merged[-SNAPSHOT_MAX_EVENTS:]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in merged)
        path.write_text(payload, encoding="utf-8")
    except Exception:
        return 0
    return len(fresh)


def load_snapshot(team_run_id: str) -> List[Dict[str, Any]]:
    """读回快照事件（按时间升序）；文件缺失或损坏返回空表。"""
    path = snapshot_path(team_run_id)
    if not path.exists():
        return []
    events: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except Exception:
                continue
            if isinstance(event, dict) and event.get("from") and event.get("to"):
                events.append(event)
    except Exception:
        return []
    events.sort(key=lambda e: (float(e.get("time") or 0), str(e.get("mail_id") or "")))
    return events


def build_lane_roster(
    members: List[Dict[str, Any]],
    leader: str,
    events: List[Dict[str, Any]],
    current_agent: str = "",
) -> List[Dict[str, Any]]:
    """合成泳道名单：leader 置顶、同名合并、快照人物兜底。

    返回 ``[{agent_name, is_leader, live, description}]``，live 表示该泳道
    在当前活跃成员表里有对应窗口。
    """
    by_name: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    if not leader:
        # 回放兜底：leader 未登记时按 task 发送数最多者推定
        counts: Dict[str, int] = {}
        for event in events:
            if event.get("kind") == "task":
                name = str(event.get("from") or "")
                counts[name] = counts.get(name, 0) + 1
        if counts:
            leader = max(counts, key=lambda name: counts[name])
    for member in members:
        name = str(member.get("agent_name") or "")
        if not name:
            continue
        if name not in by_name:
            by_name[name] = {
                "agent_name": name,
                "is_leader": name == leader,
                "live": True,
                "description": "",
            }
            order.append(name)
        capability = member.get("capability") or {}
        if not by_name[name]["description"]:
            by_name[name]["description"] = str(capability.get("role_desc") or "")
    for name in (leader, current_agent):
        if name and name not in by_name:
            by_name[name] = {"agent_name": name, "is_leader": name == leader, "live": False, "description": ""}
            order.append(name)
    for event in events:
        for name in (event.get("from"), event.get("to")):
            name = str(name or "")
            if name and name not in by_name:
                by_name[name] = {"agent_name": name, "is_leader": name == leader, "live": False, "description": ""}
                order.append(name)
    lanes = [by_name[name] for name in order]
    lanes.sort(key=lambda lane: (not lane["is_leader"], lane["agent_name"]))
    return lanes


def summary_of_event(event: Dict[str, Any], max_len: int = 160) -> str:
    """单行摘要：task 用 subject/body，reply 用 result。"""
    if event.get("kind") == "reply":
        text = event.get("result") or event.get("body") or ""
    else:
        text = event.get("body") or event.get("subject") or ""
    text = " ".join(str(text).split())
    return text[:max_len] + ("…" if len(text) > max_len else "")


def fmt_event_time(ts: Any) -> str:
    try:
        return time.strftime("%H:%M:%S", time.localtime(float(ts)))
    except (TypeError, ValueError, OSError, OverflowError):
        return "—"
