# -*- coding: utf-8 -*-
"""数据层 — SQLite 存储（收藏/历史/下载）+ QThread 异步 Worker

表结构：
- bookmarks(url PK, title, created_at, folder)
- history(url, title, visited_at, visit_count)
- downloads(id, url, path, state, bytes_received, bytes_total, created_at)

数据目录：~/.drifox/plugins/browser/data/browser.db

设计约束（闭包）：
- 不导入 app.core 或 app.widgets 内部的任何模块
- 所有文件操作直接通过 sqlite3/stdlib 完成
- 写操作快速同步执行（单条 INSERT，毫秒级）；读操作（补全/管理面板）
  走 QThread worker，避免阻塞 UI
"""

import sqlite3
import threading
import traceback
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PyQt5.QtCore import QObject, pyqtSignal
from loguru import logger

# ── 路径常量 ──────────────────────────────────────────────

_DATA_DIR = Path.home() / ".drifox" / "plugins" / "browser" / "data"
_DB_PATH = _DATA_DIR / "browser.db"

# ── 数据库初始化 ──────────────────────────────────────────

_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bookmarks (
    url         TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    folder      TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS history (
    url         TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    visited_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    visit_count INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS downloads (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    url            TEXT NOT NULL,
    path           TEXT NOT NULL DEFAULT '',
    state          TEXT NOT NULL DEFAULT 'downloading',
    bytes_received INTEGER NOT NULL DEFAULT 0,
    bytes_total    INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_history_visited ON history(visited_at DESC);
CREATE INDEX IF NOT EXISTS idx_downloads_created ON downloads(created_at DESC);
"""


def _ensure_db() -> None:
    """确保数据库文件与表结构存在（线程安全，幂等）"""
    with _lock:
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(_DB_PATH), timeout=5)
            conn.executescript(_SCHEMA)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[browser] 数据库初始化失败: {e}")


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接（row_factory=sqlite3.Row）"""
    conn = sqlite3.connect(str(_DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


# ══════════════════════════════════════════════════════════
# 写操作（同步，快速）
# ══════════════════════════════════════════════════════════


def add_bookmark(url: str, title: str = "", folder: str = "") -> bool:
    """添加/更新收藏（url 为主键，upsert），返回是否成功。"""
    _ensure_db()
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO bookmarks(url, title, folder) VALUES(?, ?, ?) "
            "ON CONFLICT(url) DO UPDATE SET title=excluded.title, folder=excluded.folder",
            (url, title, folder),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"[browser] 添加收藏失败: {e}")
        return False


def remove_bookmark(url: str) -> bool:
    _ensure_db()
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM bookmarks WHERE url=?", (url,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"[browser] 删除收藏失败: {e}")
        return False


def record_history(url: str, title: str = "") -> None:
    """记录访问历史（url 主键，visit_count 累加）"""
    if not url or url in ("about:blank",):
        return
    _ensure_db()
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO history(url, title, visited_at) VALUES(?, ?, datetime('now', 'localtime')) "
            "ON CONFLICT(url) DO UPDATE SET "
            "  title=CASE WHEN excluded.title!='' THEN excluded.title ELSE history.title END, "
            "  visited_at=excluded.visited_at, "
            "  visit_count=history.visit_count + 1",
            (url, title),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[browser] 记录历史失败: {e}")


def upsert_download(
    url: str, path: str = "", state: str = "downloading",
    bytes_received: int = 0, bytes_total: int = 0,
) -> int:
    """记录下载项，返回 id（url+path 维度 upsert）"""
    _ensure_db()
    try:
        conn = _get_conn()
        cur = conn.execute(
            "INSERT INTO downloads(url, path, state, bytes_received, bytes_total) "
            "VALUES(?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO NOTHING",
            (url, path, state, bytes_received, bytes_total),
        )
        conn.commit()
        new_id = cur.lastrowid
        conn.close()
        return new_id or 0
    except Exception as e:
        logger.error(f"[browser] 记录下载失败: {e}")
        return 0


def update_download_state(download_id: int, state: str, bytes_received: int, bytes_total: int) -> None:
    _ensure_db()
    try:
        conn = _get_conn()
        conn.execute(
            "UPDATE downloads SET state=?, bytes_received=?, bytes_total=? WHERE id=?",
            (state, bytes_received, bytes_total, download_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[browser] 更新下载状态失败: {e}")


# ══════════════════════════════════════════════════════════
# 读操作（供 worker / 补全 / 管理面板）
# ══════════════════════════════════════════════════════════


def query_history(limit: int = 200) -> List[dict]:
    """查询历史（按访问时间倒序）"""
    _ensure_db()
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT url, title, visited_at, visit_count FROM history "
            "ORDER BY visited_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"[browser] 查询历史失败: {e}")
        return []


def query_bookmarks(limit: int = 500) -> List[dict]:
    """查询收藏（按创建时间倒序）"""
    _ensure_db()
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT url, title, folder, created_at FROM bookmarks "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"[browser] 查询收藏失败: {e}")
        return []


def query_downloads(limit: int = 100) -> List[dict]:
    """查询下载记录（按创建时间倒序）"""
    _ensure_db()
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT id, url, path, state, bytes_received, bytes_total, created_at "
            "FROM downloads ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"[browser] 查询下载失败: {e}")
        return []


def query_suggestions(limit: int = 50) -> List[Tuple[str, str]]:
    """地址栏补全数据：历史 + 收藏 合并，按权重排序

    权重 = visit_count（历史）或固定 100（收藏），保证收藏靠前。
    Returns: [(url, title)]
    """
    _ensure_db()
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT url, title, visit_count FROM history ORDER BY visit_count DESC LIMIT ?",
            (limit,),
        ).fetchall()
        hist = [(r["url"], r["title"]) for r in rows]

        rows = conn.execute(
            "SELECT url, title FROM bookmarks ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        bm = [(r["url"], r["title"]) for r in rows]
        conn.close()

        # 合并去重（收藏优先）
        seen = set()
        merged: List[Tuple[str, str]] = []
        for url, title in bm + hist:
            if url in seen or not url:
                continue
            seen.add(url)
            merged.append((url, title))
        return merged[:limit]
    except Exception as e:
        logger.error(f"[browser] 查询补全失败: {e}")
        return []


def search_history(keyword: str, limit: int = 100) -> List[dict]:
    """按关键词搜索历史"""
    _ensure_db()
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT url, title, visited_at FROM history "
            "WHERE url LIKE ? OR title LIKE ? "
            "ORDER BY visited_at DESC LIMIT ?",
            (f"%{keyword}%", f"%{keyword}%", limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"[browser] 搜索历史失败: {e}")
        return []


def clear_history() -> int:
    """清空历史，返回删除条数"""
    _ensure_db()
    try:
        conn = _get_conn()
        cur = conn.execute("DELETE FROM history")
        conn.commit()
        n = cur.rowcount
        conn.close()
        return n
    except Exception as e:
        logger.error(f"[browser] 清空历史失败: {e}")
        return 0


# ══════════════════════════════════════════════════════════
# 异步 Worker（QThread 模式，参考 context-usage-stats）
# ══════════════════════════════════════════════════════════


class _DataWorker(QObject):
    """后台线程执行数据库读取（补全/管理面板数据）"""

    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, query_name: str, *args, **kwargs):
        super().__init__()
        self._query_name = query_name
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            fn = {
                "history": query_history,
                "bookmarks": query_bookmarks,
                "downloads": query_downloads,
                "suggestions": query_suggestions,
                "search_history": search_history,
            }.get(self._query_name)
            if fn is None:
                raise ValueError(f"未知查询: {self._query_name}")
            data = fn(*self._args, **self._kwargs)
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(f"{e}\n{traceback.format_exc()}")


class AsyncDataLoader(QObject):
    """异步数据加载器 — 管理 worker 线程生命周期

    用法：
        loader = AsyncDataLoader(self)
        loader.load("suggestions", self._on_suggestions, limit=50)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._threads = []

    def load(self, query_name: str, on_done: Callable, on_error: Optional[Callable] = None, *args, **kwargs):
        """启动一次异步查询，结果通过 on_done(data) 回调"""
        from PyQt5.QtCore import QThread

        worker = _DataWorker(query_name, *args, **kwargs)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._make_done_cb(on_done, worker, thread))
        if on_error is not None:
            worker.error.connect(self._make_error_cb(on_error, worker, thread))
        else:
            worker.error.connect(self._make_error_cb(lambda e: logger.error(f"[browser] {e}"), worker, thread))
        self._threads.append(thread)
        thread.start()

    def _make_done_cb(self, on_done, worker, thread):
        def _cb(data):
            try:
                on_done(data)
            except Exception:
                pass
            self._finish(worker, thread)
        return _cb

    def _make_error_cb(self, on_error, worker, thread):
        def _cb(err):
            try:
                on_error(err)
            except Exception:
                pass
            self._finish(worker, thread)
        return _cb

    def _finish(self, worker, thread):
        thread.quit()
        thread.wait(500)
        if thread in self._threads:
            self._threads.remove(thread)
        worker.deleteLater()
        thread.deleteLater()

    def cleanup(self):
        """释放所有线程（卡片关闭时调用）"""
        for thread in list(self._threads):
            try:
                thread.quit()
                thread.wait(300)
                thread.deleteLater()
            except RuntimeError:
                pass
        self._threads.clear()
