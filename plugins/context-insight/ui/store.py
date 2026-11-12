# -*- coding: utf-8 -*-
"""会话记录适配层 —— 只处理能力池返回的 history 记录，不直读宿主数据库。

``session.history`` 能力返回的会话记录是宿主 HistoryManager 的公开结构，
字段语义以宿主为准；本模块只做「记录 → SessionMeta / messages」的投影。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _int_of(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float_of(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _json_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        import json

        data = json.loads(str(value))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@dataclass
class SessionMeta:
    session_id: str
    title: str = ""
    project: str = ""
    worktree_path: str = ""
    created_at: str = ""
    updated_at: str = ""
    message_count: int = 0
    agent_name: str = ""
    team_run_id: str = ""
    team_name: str = ""
    team_members: str = ""
    preview: str = ""
    pinned: int = 0
    context_usage: int = 0
    last_api_prompt_tokens: int = 0
    last_api_message_count: int = 0
    last_api_prompt_from_usage: Optional[int] = None
    token_calibration: float = 0.0
    token_calibration_model: str = ""
    system_prompt: str = ""
    compaction_state: Dict[str, Any] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        return f"{self.updated_at}|{int(self.message_count or 0)}"


def meta_from_record(record: Dict[str, Any]) -> SessionMeta:
    """把 HistoryManager 的会话记录投影成 SessionMeta。"""
    record = record or {}
    updated = str(
        record.get("updated_at")
        or record.get("last_time")
        or record.get("saved_at")
        or ""
    )
    created = str(record.get("created_at") or record.get("saved_at") or updated)
    last_from_usage = record.get("last_api_prompt_from_usage")
    return SessionMeta(
        session_id=str(record.get("session_id") or ""),
        title=str(record.get("title") or ""),
        project=str(record.get("project") or "默认项目"),
        worktree_path=str(record.get("worktree_path") or ""),
        created_at=created,
        updated_at=updated,
        message_count=_int_of(record.get("message_count")),
        agent_name=str(record.get("agent_name") or ""),
        team_run_id=str(record.get("team_run_id") or ""),
        team_name=str(record.get("team_name") or ""),
        team_members=str(record.get("team_members") or ""),
        preview=str(record.get("preview") or ""),
        pinned=1 if record.get("pinned") else 0,
        context_usage=_int_of(record.get("context_usage")),
        last_api_prompt_tokens=_int_of(record.get("last_api_prompt_tokens")),
        last_api_message_count=_int_of(record.get("last_api_message_count")),
        last_api_prompt_from_usage=(
            None if last_from_usage is None else _int_of(last_from_usage)
        ),
        token_calibration=_float_of(record.get("token_calibration")),
        token_calibration_model=str(record.get("token_calibration_model") or ""),
        system_prompt=str(record.get("system_prompt") or ""),
        compaction_state=_json_dict(record.get("compaction_state")),
    )


def messages_from_record(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """取全量消息（HistoryManager 已合并剥离字段）。"""
    raw = (record or {}).get("messages")
    if not isinstance(raw, list):
        return []
    return [m for m in raw if isinstance(m, dict)]
