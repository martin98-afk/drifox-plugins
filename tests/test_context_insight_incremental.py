# -*- coding: utf-8 -*-
"""context-insight 增量索引测试

以包形式从文件加载插件 ui 目录（不执行 __init__.py，避免拉起整套 UI），
验证：轻量指纹命中不读全量记录、内容变化才重算、元数据单独变化不重算、
索引落盘可复用。
"""

import importlib
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("PyQt5")

_UI_DIR = Path(__file__).resolve().parent.parent / "plugins" / "context-insight" / "ui"
_PKG = "ci_under_test"


def _load_collector():
    if _PKG not in sys.modules:
        pkg = types.ModuleType(_PKG)
        pkg.__path__ = [str(_UI_DIR)]  # type: ignore[attr-defined]
        sys.modules[_PKG] = pkg
    return importlib.import_module(f"{_PKG}.collector")


@pytest.fixture()
def collector(tmp_path):
    module = _load_collector()
    plugin_config = importlib.import_module(f"{_PKG}.plugin_config")
    module.clear_memory_cache()
    plugin_config.set_data_root(tmp_path)
    yield module
    module.clear_memory_cache()


def _record(sid: str, *, count: int, last_time: str, title: str, project: str = "默认项目"):
    return {
        "session_id": sid,
        "title": title,
        "project": project,
        "saved_at": "2026-01-01 00:00:00",
        "updated_at": last_time,
        "last_time": last_time,
        "message_count": count,
        "messages": [
            {"role": "user", "content": "你好，帮我看看这段代码"},
            {"role": "assistant", "content": "好的，先看结构"},
        ],
    }


def _entry(record):
    return {
        "session_id": record["session_id"],
        "title": record["title"],
        "project": record["project"],
        "saved_at": record["saved_at"],
        "last_time": record["last_time"],
        "message_count": record["message_count"],
        "worktree_path": "",
        "agent_name": "",
        "team_run_id": "",
        "team_name": "",
        "team_members": "",
    }


class _History:
    def __init__(self, records):
        self.records = records
        self.reads = []

    def list_fn(self):
        return [_entry(r) for r in self.records.values()]

    def session_fn(self, sid):
        self.reads.append(sid)
        return self.records.get(sid)


def test_first_scan_reads_all_then_hits_cache(collector, tmp_path):
    records = {
        "a": _record("a", count=1, last_time="2026-01-01 10:00:00", title="会话 A"),
        "b": _record("b", count=3, last_time="2026-01-02 10:00:00", title="会话 B"),
    }
    history = _History(records)
    out, changed = collector.scan_index(history.list_fn, history.session_fn)
    assert changed == 2
    assert sorted(history.reads) == ["a", "b"]
    assert len(out) == 2

    history.reads.clear()
    out2, changed2 = collector.scan_index(
        history.list_fn, history.session_fn, cached=out
    )
    assert changed2 == 0
    assert history.reads == []  # 全部命中，零全量读取
    assert {k: v["fingerprint"] for k, v in out2.items()} == {
        k: v["fingerprint"] for k, v in out.items()
    }


def test_content_change_recomputes_only_that_session(collector):
    records = {
        "a": _record("a", count=1, last_time="2026-01-01 10:00:00", title="会话 A"),
        "b": _record("b", count=3, last_time="2026-01-02 10:00:00", title="会话 B"),
    }
    history = _History(records)
    out, _ = collector.scan_index(history.list_fn, history.session_fn)

    records["b"]["message_count"] = 5
    records["b"]["last_time"] = "2026-01-03 10:00:00"
    history.reads.clear()
    out2, changed = collector.scan_index(
        history.list_fn, history.session_fn, cached=out
    )
    assert changed == 1
    assert history.reads == ["b"]
    assert out2["b"]["message_count"] == 5


def test_meta_only_change_reuses_summary(collector):
    records = {
        "a": _record("a", count=1, last_time="2026-01-01 10:00:00", title="会话 A"),
    }
    history = _History(records)
    out, _ = collector.scan_index(history.list_fn, history.session_fn)
    before = out["a"]["cost_usd"]

    records["a"]["title"] = "改名后的会话"
    history.reads.clear()
    out2, changed = collector.scan_index(
        history.list_fn, history.session_fn, cached=out
    )
    assert changed == 0
    assert history.reads == []
    assert out2["a"]["title"] == "改名后的会话"
    assert out2["a"]["cost_usd"] == before


def test_entry_without_fingerprint_falls_back_to_full_read(collector):
    records = {"a": _record("a", count=1, last_time="2026-01-01 10:00:00", title="会话 A")}
    history = _History(records)

    def blind_list():
        entry = _entry(records["a"])
        entry["last_time"] = ""
        entry["saved_at"] = ""
        return [entry]

    out, changed = collector.scan_index(blind_list, history.session_fn)
    assert changed == 1
    assert history.reads == ["a"]
    history.reads.clear()
    _, changed2 = collector.scan_index(blind_list, history.session_fn, cached=out)
    assert changed2 == 1  # 无指纹无法判缓存，保守重算
    assert history.reads == ["a"]


def test_index_persisted_and_reloaded(collector):
    records = {"a": _record("a", count=1, last_time="2026-01-01 10:00:00", title="会话 A")}
    history = _History(records)
    out, _ = collector.scan_index(history.list_fn, history.session_fn)
    collector._save_index(out)
    collector.clear_memory_cache()

    loaded = collector.cached_summaries()
    assert len(loaded) == 1
    assert loaded[0]["session_id"] == "a"
    assert loaded[0]["version"] == collector._INDEX_VERSION
