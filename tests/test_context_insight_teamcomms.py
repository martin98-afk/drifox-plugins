# -*- coding: utf-8 -*-
"""context-insight 团队消息轨迹测试

宿主 TeamManager 自 create_team 起（0.7.3+）改为「全链路 DEFAULT_TEAM 目录 +
run_id 粒度」：团队名退化为 team_label 展示字段，不再建 team_name 目录。
回归锁定：gather_team_comms 必须按 default 目录 + run_id 过滤查询，
把会话记录里的 team_name 展示名当查询键会静默拿到空数据（消息轨迹整卡为空）。
"""

import importlib
import json
import sys
import types
from pathlib import Path

import pytest

_UI_DIR = Path(__file__).resolve().parent.parent / "plugins" / "context-insight" / "ui"
_PKG = "ci_comms_under_test"


def _load_teamcomms():
    if _PKG not in sys.modules:
        pkg = types.ModuleType(_PKG)
        pkg.__path__ = [str(_UI_DIR)]  # type: ignore[attr-defined]
        sys.modules[_PKG] = pkg
    return importlib.import_module(f"{_PKG}.teamcomms")


class _FakeTeamRead:
    """按宿主 TeamManager 源码语义模拟：目录路由 + run_id 字段过滤。"""

    def __init__(self, root: Path):
        self.root = root

    def _team_data(self, team_name):
        p = self.root / team_name / "team.json"
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def get_members(self, team_name="default", run_id=None):
        members = list((self._team_data(team_name).get("members") or {}).values())
        if run_id is None:
            return members
        if run_id == "":
            return [m for m in members if not m.get("run_id")]
        return [m for m in members if m.get("run_id") == run_id]

    def get_leader_window_id(self, team_name="default"):
        return str(self._team_data(team_name).get("leader_window_id") or "")

    def get_mailbox_mails(self, window_id, team_name="default"):
        d = self.root / team_name / "mailboxes" / window_id
        if not d.exists():
            return []
        out = []
        for f in sorted(d.glob("mail_*.json")):
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                pass
        return out


def _seed(root: Path, run_id: str):
    """构造一个宿主形态的团队：default 目录、2 成员、leader + 2 邮件。"""
    (root / "default").mkdir(parents=True)
    (root / "default" / "team.json").write_text(
        json.dumps(
            {
                "leader_window_id": "win_01",
                "members": {
                    "win_01": {"window_id": "win_01", "agent_name": "leader", "run_id": run_id},
                    "win_02": {"window_id": "win_02", "agent_name": "build", "run_id": run_id},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    mb = root / "default" / "mailboxes"
    (mb / "win_01").mkdir(parents=True)
    (mb / "win_02").mkdir(parents=True)
    (mb / "win_02" / "mail_1.json").write_text(
        json.dumps(
            {
                "id": "mail_1",
                "type": "task",
                "team_name": "default",
                "from_window": "win_01",
                "from_agent": "leader",
                "to_window": "win_02",
                "to_agent": "build",
                "subject": "修 bug",
                "body": "修复崩溃",
                "status": "done",
                "created_at": 1000.0,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (mb / "win_02" / "mail_2.json").write_text(
        json.dumps(
            {
                "id": "mail_2",
                "type": "reply",
                "team_name": "default",
                "reply_to": "mail_1",
                "from_window": "win_02",
                "from_agent": "build",
                "to_window": "win_01",
                "to_agent": "leader",
                "subject": "Re: 任务结果 (完成)",
                "body": "done",
                "result": "已修复",
                "status": "done",
                "success": True,
                "created_at": 2000.0,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    # 另一个 run 的成员与邮件（多团队并存，验证 run_id 过滤隔离）
    (root / "default" / "team.json").write_text(
        json.dumps(
            {
                "leader_window_id": "win_01",
                "members": {
                    "win_01": {"window_id": "win_01", "agent_name": "leader", "run_id": run_id},
                    "win_02": {"window_id": "win_02", "agent_name": "build", "run_id": run_id},
                    "win_09": {"window_id": "win_09", "agent_name": "other", "run_id": "run-other"},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (mb / "win_09").mkdir(parents=True)
    (mb / "win_09" / "mail_9.json").write_text(
        json.dumps(
            {
                "id": "mail_9",
                "type": "task",
                "team_name": "default",
                "from_window": "win_01",
                "from_agent": "leader",
                "to_window": "win_09",
                "to_agent": "other",
                "subject": "其他团队任务",
                "body": "",
                "status": "done",
                "created_at": 3000.0,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_gather_by_run_id_filters_members_and_events(tmp_path):
    tc = _load_teamcomms()
    _seed(tmp_path, "run-a")
    out = tc.gather_team_comms(_FakeTeamRead(tmp_path), run_id="run-a")
    names = {m["agent_name"] for m in out["members"]}
    assert names == {"leader", "build"}  # run-other 成员被过滤
    assert out["leader"] == "leader"
    ids = [e["mail_id"] for e in out["events"]]
    assert ids == ["mail_1", "mail_2"]  # 邮箱按 default 目录聚合，时间升序
    assert out["events"][0]["kind"] == "task"
    assert out["events"][1]["kind"] == "reply" and out["events"][1]["success"] is True


def test_gather_without_run_id_falls_back_to_full_roster(tmp_path):
    tc = _load_teamcomms()
    _seed(tmp_path, "run-a")
    out = tc.gather_team_comms(_FakeTeamRead(tmp_path))
    assert {m["agent_name"] for m in out["members"]} == {"leader", "build", "other"}


def test_display_label_as_key_yields_nothing(tmp_path):
    """回归：展示名（会话记录 team_name）不是目录键也不是 run_id，查询必须为空。

    这正是「消息轨迹整卡为空」的根因行为——锁定它防止改回旧协议。
    """
    tc = _load_teamcomms()
    _seed(tmp_path, "run-a")
    out = tc.gather_team_comms(_FakeTeamRead(tmp_path), run_id="default-team")
    assert out["members"] == []
    assert out["events"] == []


def test_gather_survives_missing_team_dir(tmp_path):
    tc = _load_teamcomms()
    out = tc.gather_team_comms(_FakeTeamRead(tmp_path))
    assert out == {"members": [], "leader": "", "events": []}


def test_snapshot_roundtrip_and_merge(tmp_path):
    tc = _load_teamcomms()
    import importlib

    pc = importlib.import_module(f"{_PKG}.plugin_config")
    pc.set_data_root(tmp_path)

    events = [
        {"mail_id": "m1", "kind": "task", "from": "leader", "to": "build", "time": 1.0},
        {"mail_id": "m2", "kind": "reply", "from": "build", "to": "leader", "time": 2.0},
    ]
    assert tc.append_snapshot("run-a", events) == 2
    # 增量：同 id 不重复追加
    assert tc.append_snapshot("run-a", events) == 0
    assert tc.append_snapshot("run-a", [dict(events[0], body="x")]) == 0

    loaded = tc.load_snapshot("run-a")
    assert [e["mail_id"] for e in loaded] == ["m1", "m2"]
    assert tc.load_snapshot("run-missing") == []
