# -*- coding: utf-8 -*-
"""数据层 — SQLite 读取 + 模块级缓存（欢迎卡片 tab 专用）

设计约束（闭包）：
- 不导入 app.core 或 app.widgets 内部的任何模块
- 所有文件操作直接通过 sqlite3/stdlib 完成
- 基于 .drifox/sessions.db 文件直接读取数据
- render_func 在主线程同步调用 → 查询必须轻量 + 模块级缓存
"""

import sqlite3
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger


# ── 路径常量 ──────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEV_DB_PATH = _PROJECT_ROOT / ".drifox" / "sessions.db"
_USER_DB_PATH = Path.home() / ".drifox" / "sessions.db"


def _find_db() -> Optional[Path]:
    """查找 sessions.db 文件路径（开发环境 → 用户目录兜底）"""
    if _DEV_DB_PATH.exists():
        return _DEV_DB_PATH
    if _USER_DB_PATH.exists():
        return _USER_DB_PATH
    return None


# ── Token 快速估算 ────────────────────────────────────────


def _fast_estimate_tokens(text: str) -> int:
    """快速估算文本的 token 数（无需 tiktoken 依赖）

    经验公式（cl100k_base 类分词器近似，覆盖 GPT/DeepSeek/Qwen/Claude）：
    - 中文约 1.2 token/字
    - 英文/代码约 1 token / 4 字符
    """
    if not text:
        return 0
    chinese = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    non_chinese = len(text) - chinese
    estimated = int(chinese * 1.2 + non_chinese / 4.0)
    return max(1, estimated)


# ── SQLite 数据读取 ──────────────────────────────────────


def _get_db_connection() -> Optional[sqlite3.Connection]:
    """获取 SQLite 数据库连接（只读模式）"""
    db_path = _find_db()
    if db_path is None:
        return None
    try:
        conn = sqlite3.connect(str(db_path), timeout=3)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.error(f"[ContextStats] 无法打开数据库: {e}")
        return None


def _fetch_stats() -> dict:
    """从数据库读取近 14 天统计

    Returns:
        dict with keys:
        - daily_tokens: List[Tuple[str, int]] (MM-DD, 估算 token 数), 最近 14 天
        - daily_messages: List[Tuple[str, int]] (MM-DD, 消息数), 最近 14 天
        - total_tokens: int（近 14 天 token 合计）
        - total_messages: int（近 14 天消息合计）
        - error: Optional[str]
    """
    result = {
        "daily_tokens": [],
        "daily_messages": [],
        "total_tokens": 0,
        "total_messages": 0,
        "error": None,
    }

    conn = _get_db_connection()
    if conn is None:
        result["error"] = "无法连接到数据库"
        return result

    try:
        cursor = conn.cursor()

        # 1. ═══ 最近 14 天日期轴 ═══
        today = datetime.now()
        date_labels = [
            (today - timedelta(days=i)).strftime("%m-%d") for i in range(13, -1, -1)
        ]
        daily_tokens_map: Dict[str, int] = {dl: 0 for dl in date_labels}
        daily_messages_map: Dict[str, int] = {dl: 0 for dl in date_labels}

        # 2. ═══ 按日聚合 token 用量（context_usage > 0 的会话） ═══
        cursor.execute(
            "SELECT DATE(created_at) as day, COALESCE(SUM(context_usage), 0) as total_tokens "
            "FROM sessions "
            "WHERE created_at >= date('now', '-13 days') "
            "AND project NOT LIKE '__archived__%' "
            "AND context_usage > 0 "
            "GROUP BY DATE(created_at) ORDER BY day"
        )
        for row in cursor.fetchall():
            day_str = row["day"]
            if not day_str:
                continue
            try:
                label = datetime.strptime(day_str, "%Y-%m-%d").strftime("%m-%d")
                daily_tokens_map[label] = row["total_tokens"]
            except (ValueError, TypeError):
                pass

        # 3. ═══ 按日聚合消息量 ═══
        cursor.execute(
            "SELECT DATE(created_at) as day, COUNT(*) as cnt, "
            "COALESCE(SUM(message_count), 0) as msgs "
            "FROM sessions "
            "WHERE created_at >= date('now', '-13 days') "
            "AND project NOT LIKE '__archived__%' "
            "GROUP BY DATE(created_at) ORDER BY day"
        )
        for row in cursor.fetchall():
            day_str = row["day"]
            if not day_str:
                continue
            try:
                label = datetime.strptime(day_str, "%Y-%m-%d").strftime("%m-%d")
                daily_messages_map[label] = row["msgs"]
            except (ValueError, TypeError):
                pass

        # 4. ═══ 回退：context_usage=0 的旧会话用 messages 估算 token ═══
        cursor.execute(
            "SELECT DATE(created_at) as day, messages "
            "FROM sessions "
            "WHERE created_at >= date('now', '-13 days') "
            "AND project NOT LIKE '__archived__%' "
            "AND (context_usage IS NULL OR context_usage = 0) "
            "AND messages IS NOT NULL AND messages != '' "
            "ORDER BY created_at DESC"
        )
        for row in cursor.fetchall():
            day_str = row["day"]
            if not day_str:
                continue
            try:
                label = datetime.strptime(day_str, "%Y-%m-%d").strftime("%m-%d")
                msg_data = row["messages"]
                if isinstance(msg_data, (str, bytes)):
                    tokens = _fast_estimate_tokens(str(msg_data)[:100000])
                    daily_tokens_map[label] = daily_tokens_map.get(label, 0) + tokens
            except Exception:
                pass

        # 5. ═══ 组装结果 ═══
        for dl in date_labels:
            result["daily_tokens"].append((dl, daily_tokens_map[dl]))
            result["daily_messages"].append((dl, daily_messages_map[dl]))

        result["total_tokens"] = sum(v for _, v in result["daily_tokens"])
        result["total_messages"] = sum(v for _, v in result["daily_messages"])

        conn.close()
    except Exception as e:
        result["error"] = f"{e}"
        logger.error(f"[ContextStats] 数据读取失败: {e}\n{traceback.format_exc()}")
        try:
            conn.close()
        except Exception:
            pass

    return result


# ── 模块级缓存 ───────────────────────────────────────────

_cache: Dict[str, object] = {}


def get_stats() -> dict:
    """带模块级缓存的统计读取（主线程安全、轻量）

    缓存 key = (db 文件 mtime_ns, 当天日期)：
    - db 文件变化（新会话写入）→ 自动失效重查
    - 跨天 → 日期键变化自动重查
    - 无 db → 缓存空结果避免反复失败查询
    """
    global _cache

    db_path = _find_db()
    if db_path is None:
        return {
            "daily_tokens": [],
            "daily_messages": [],
            "total_tokens": 0,
            "total_messages": 0,
            "error": "无法连接到数据库",
        }

    try:
        mtime_ns = db_path.stat().st_mtime_ns
    except OSError:
        mtime_ns = 0

    day_key = datetime.now().strftime("%Y-%m-%d")
    cache_key = (mtime_ns, day_key)

    cached = _cache.get("key")
    if cached == cache_key:
        return _cache["data"]

    data = _fetch_stats()
    _cache = {"key": cache_key, "data": data}
    return data
