# -*- coding: utf-8 -*-
"""后台采集器 —— 全部数据来自能力池的 session.history，不直读宿主数据库。

线程模型：
- ``IndexWorker``：QThread，扫全库 → 发 ``finished(list[dict])``。
- ``DetailWorker``：QThread，分析单个会话 → 发 ``finished(SessionAnalysis)``。

历史记录由宿主 ``session.history`` 能力提供（dict of closures）：
``list()`` 返回轻量列表，``session(session_id)`` 返回全量记录。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List

from loguru import logger
from PyQt5.QtCore import QThread, pyqtSignal

from .analyzer import analyze_session, summarize_for_index
from .plugin_config import plugin_data_dir
from .store import messages_from_record, meta_from_record
from .tokens import count_tools

_INDEX_VERSION = 2
_CACHE_LOCK = threading.Lock()
_SUMMARY_CACHE: Dict[str, Dict[str, Any]] = {}
_INDEX_LOADED = False


def _index_path() -> Path:
    return plugin_data_dir() / "index.json"


def _load_index() -> Dict[str, Dict[str, Any]]:
    global _INDEX_LOADED
    with _CACHE_LOCK:
        if _INDEX_LOADED:
            return _SUMMARY_CACHE
        _INDEX_LOADED = True
        path = _index_path()
        if not path.exists():
            return _SUMMARY_CACHE
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[context-insight] 索引读取失败，按空表重扫: {e}")
            return _SUMMARY_CACHE
        if not isinstance(data, dict) or data.get("version") != _INDEX_VERSION:
            return _SUMMARY_CACHE
        sessions = data.get("sessions")
        if isinstance(sessions, dict):
            for sid, item in sessions.items():
                if isinstance(item, dict):
                    _SUMMARY_CACHE[str(sid)] = item
        return _SUMMARY_CACHE


def _save_index(summaries: Dict[str, Dict[str, Any]]) -> None:
    path = _index_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": _INDEX_VERSION, "sessions": summaries}
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except Exception as e:
        logger.warning(f"[context-insight] 索引写入失败（本轮不持久化）: {e}")


def clear_memory_cache() -> None:
    global _INDEX_LOADED
    with _CACHE_LOCK:
        _SUMMARY_CACHE.clear()
        _INDEX_LOADED = False


def cached_summaries() -> List[Dict[str, Any]]:
    with _CACHE_LOCK:
        return [dict(v) for v in _SUMMARY_CACHE.values()]


def _history_call(history: Any, name: str):
    """能力返回的 dict of closures；兼容 Mapping 与对象属性。"""
    if history is None:
        return None
    if hasattr(history, "get"):
        fn = history.get(name)
        if fn is not None:
            return fn
    return getattr(history, name, None)


class IndexWorker(QThread):
    """全库增量扫描。"""

    progress = pyqtSignal(int, int)
    finished_ok = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, history: Any, parent=None):
        super().__init__(parent)
        self._history = history
        self._abort = threading.Event()

    def stop(self) -> None:
        self._abort.set()

    def run(self) -> None:  # noqa: D401
        list_fn = _history_call(self._history, "list")
        session_fn = _history_call(self._history, "session")
        if not callable(list_fn) or not callable(session_fn):
            self.failed.emit("session.history 能力缺少 list/session 方法")
            return
        try:
            entries = list_fn() or []
            if not entries:
                self.finished_ok.emit([])
                return
            cached = _load_index()
            out: Dict[str, Dict[str, Any]] = {}
            total = len(entries)
            for i, entry in enumerate(entries, 1):
                if self._abort.is_set():
                    return
                sid = str((entry or {}).get("session_id") or "")
                if not sid:
                    continue
                record = session_fn(sid)
                if not record:
                    continue
                meta = meta_from_record(record)
                old = cached.get(sid)
                if old and old.get("fingerprint") == meta.fingerprint and old.get("version") == _INDEX_VERSION:
                    out[sid] = old
                    if i % 8 == 0 or i == total:
                        self.progress.emit(i, total)
                    continue
                messages = messages_from_record(record)
                analysis = analyze_session(meta, messages)
                out[sid] = summarize_for_index(analysis)
                if i % 4 == 0 or i == total:
                    self.progress.emit(i, total)
            with _CACHE_LOCK:
                _SUMMARY_CACHE.clear()
                _SUMMARY_CACHE.update(out)
            _save_index(out)
            self.finished_ok.emit([dict(v) for v in out.values()])
        except Exception as e:  # noqa: BLE001
            logger.exception(f"[context-insight] 索引扫描失败: {e}")
            self.failed.emit(str(e))


class DetailWorker(QThread):
    """单会话深度分析。"""

    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        session_id: str,
        *,
        history: Any = None,
        schema_fn=None,
        parent=None,
    ):
        super().__init__(parent)
        self._session_id = session_id
        self._history = history
        self._schema_fn = schema_fn
        self._abort = threading.Event()

    def stop(self) -> None:
        self._abort.set()

    def run(self) -> None:  # noqa: D401
        try:
            session_fn = _history_call(self._history, "session")
            if not callable(session_fn):
                self.failed.emit("session.history 能力缺少 session 方法")
                return
            record = session_fn(self._session_id)
            if not record:
                self.failed.emit("会话不存在或已删除")
                return
            if self._abort.is_set():
                return
            meta = meta_from_record(record)
            messages = messages_from_record(record)

            tools_hint = 0
            tools_source = "current-schema"
            if callable(self._schema_fn):
                try:
                    schema = self._schema_fn(meta.agent_name or "") or []
                    tools_hint = count_tools(schema)
                except Exception as e:  # noqa: BLE001
                    logger.debug(f"[context-insight] 工具 schema 计数失败: {e}")
                    tools_hint = 0

            analysis = analyze_session(
                meta,
                messages,
                tools_tokens_hint=tools_hint,
                tools_source_hint=tools_source,
            )
            self.finished_ok.emit(analysis)
        except Exception as e:  # noqa: BLE001
            logger.exception(f"[context-insight] 会话分析失败: {e}")
            self.failed.emit(str(e))
