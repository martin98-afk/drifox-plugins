# -*- coding: utf-8 -*-
"""后台采集器 —— 全部数据来自能力池的 session.history，不直读宿主数据库。

线程模型：
- ``IndexWorker``：QThread，扫全库 → 发 ``finished(list[dict])``。
- ``DetailWorker``：QThread，分析单个会话 → 发 ``finished(SessionAnalysis)``。

历史记录由宿主 ``session.history`` 能力提供（dict of closures）：
``list()`` 返回轻量列表，``session(session_id)`` 返回全量记录。

增量口径：轻量列表已带 ``last_time`` / ``message_count``，指纹命中即复用旧
摘要（元数据用轻量条目覆盖），完全跳过 ``session()`` 的全量反序列化；只有
内容变化或新增的会话才真正读消息并重算。
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from loguru import logger
from PyQt5.QtCore import QThread, pyqtSignal

from .analyzer import analyze_session, summarize_for_index
from .plugin_config import plugin_data_dir
from .store import entry_fingerprint, messages_from_record, meta_from_entry, meta_from_record
from .tokens import count_tools

_INDEX_VERSION = 3
_CACHE_LOCK = threading.Lock()
_SUMMARY_CACHE: Dict[str, Dict[str, Any]] = {}
_INDEX_LOADED = False

# 扫描互斥：洞察页与会话页可能同时请求刷新，只允许一个 IndexWorker 在跑
_SCAN_LOCK = threading.Lock()
_SCANNING = False
_LAST_SCAN_AT: float = 0.0

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
    """内存快照；首次调用直接读磁盘索引，UI 首帧无需等扫描。"""
    _load_index()
    with _CACHE_LOCK:
        return [dict(v) for v in _SUMMARY_CACHE.values()]

def scan_state() -> Tuple[bool, float]:
    """(是否正在扫描, 距上次扫描结束的秒数)。"""
    with _SCAN_LOCK:
        age = time.monotonic() - _LAST_SCAN_AT if _LAST_SCAN_AT else float("inf")
        return _SCANNING, age

def _begin_scan() -> bool:
    global _SCANNING
    with _SCAN_LOCK:
        if _SCANNING:
            return False
        _SCANNING = True
        return True

def _end_scan() -> None:
    global _SCANNING, _LAST_SCAN_AT
    with _SCAN_LOCK:
        _SCANNING = False
        _LAST_SCAN_AT = time.monotonic()

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
        self._owns_scan = False

    def stop(self) -> None:
        self._abort.set()

    def run(self) -> None:  # noqa: D401
        list_fn = _history_call(self._history, "list")
        session_fn = _history_call(self._history, "session")
        if not callable(list_fn) or not callable(session_fn):
            self.failed.emit("session.history 能力缺少 list/session 方法")
            return
        # 已有扫描在跑：直接回当前快照，避免两页并发全库扫
        if not _begin_scan():
            self.finished_ok.emit(cached_summaries())
            return
        self._owns_scan = True
        try:
            cached = _load_index()
            out, changed = scan_index(
                list_fn,
                session_fn,
                abort=self._abort,
                progress=self.progress.emit,
                cached=cached,
            )
            if self._abort.is_set():
                return
            with _CACHE_LOCK:
                _SUMMARY_CACHE.clear()
                _SUMMARY_CACHE.update(out)
            if changed or set(out) != set(cached):
                _save_index(out)
            self.finished_ok.emit([dict(v) for v in out.values()])
        except Exception as e:  # noqa: BLE001
            logger.exception(f"[context-insight] 索引扫描失败: {e}")
            self.failed.emit(str(e))
        finally:
            if self._owns_scan:
                _end_scan()


def scan_index(
    list_fn,
    session_fn,
    *,
    abort: Any = None,
    progress: Any = None,
    cached: Dict[str, Dict[str, Any]] | None = None,
) -> Tuple[Dict[str, Dict[str, Any]], int]:
    """全库增量扫描核心（无 Qt 依赖，便于测试）。

    轻量列表条目已带 ``last_time`` / ``message_count``：指纹命中即复用旧摘要，
    只用条目覆盖展示元数据，**不调用** ``session_fn``；内容变化或新增的会话
    才读全量记录重算。返回 (摘要表, 重算条数)。
    """
    entries = list_fn() or []
    if not entries:
        return {}, 0
    cached = cached or {}
    out: Dict[str, Dict[str, Any]] = {}
    total = len(entries)
    changed = 0
    for i, entry in enumerate(entries, 1):
        if abort is not None and abort.is_set():
            return out, changed
        entry = entry or {}
        sid = str(entry.get("session_id") or "")
        if not sid:
            continue
        fingerprint = entry_fingerprint(entry)
        old = cached.get(sid)
        if (
            fingerprint
            and old
            and old.get("version") == _INDEX_VERSION
            and old.get("fingerprint") == fingerprint
        ):
            # 内容未变：复用摘要，只用轻量条目刷新展示元数据
            merged = dict(old)
            merged.update(meta_from_entry(entry))
            out[sid] = merged
        else:
            record = session_fn(sid)
            if not record:
                continue
            meta = meta_from_record(record)
            analysis = analyze_session(meta, messages_from_record(record))
            summary = summarize_for_index(analysis)
            summary["version"] = _INDEX_VERSION
            if fingerprint:
                summary["fingerprint"] = fingerprint
            summary.update(meta_from_entry(entry))
            out[sid] = summary
            changed += 1
        if progress is not None and (i % 8 == 0 or i == total):
            progress(i, total)
    return out, changed

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
