# -*- coding: utf-8 -*-
"""数据层 — SQLite 读取 + 模块级缓存（欢迎卡片 tab 专用）

设计约束（闭包）：
- 不导入 app.core 或 app.widgets 内部的任何模块
- 所有文件操作直接通过 sqlite3/stdlib 完成
- 基于 .drifox/sessions.db 文件直接读取数据
- render_func 在主线程同步调用 → 查询必须轻量 + 模块级缓存
"""

import sqlite3
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger


# ── 路径常量 ──────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_DEV_DB_PATH = _PROJECT_ROOT / ".drifox" / "sessions.db"
_USER_DB_PATH = Path.home() / ".drifox" / "sessions.db"

# 探测结果缓存：db 文件运行期不会移动，避免每次渲染都 stat 两条路径
_found_db_path: Optional[Path] = None


def _find_db() -> Optional[Path]:
    """查找 sessions.db 文件路径（开发环境 → 用户目录兜底）"""
    global _found_db_path
    if _found_db_path is not None and _found_db_path.exists():
        return _found_db_path
    _found_db_path = None
    if _DEV_DB_PATH.exists():
        _found_db_path = _DEV_DB_PATH
    elif _USER_DB_PATH.exists():
        _found_db_path = _USER_DB_PATH
    return _found_db_path


# ── Token 快速估算 ────────────────────────────────────────

# 删除表：删除全部 CJK 统一表意文字后长度差即中文字符数。
# str.translate 走 C 层实现，比逐字符 Python 循环快 ~2.5x（9 万字符 ≈ 4ms）。
_CJK_DELETE_TABLE = str.maketrans("", "", "".join(map(chr, range(0x4E00, 0x9FFF + 1))))


def _fast_estimate_tokens(text: str) -> int:
    """快速估算文本的 token 数（无需 tiktoken 依赖）

    经验公式（cl100k_base 类分词器近似，覆盖 GPT/DeepSeek/Qwen/Claude）：
    - 中文约 1.2 token/字
    - 英文/代码约 1 token / 4 字符
    """
    if not text:
        return 0
    chinese = len(text) - len(text.translate(_CJK_DELETE_TABLE))
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

        # 2. ═══ 单次聚合：token 用量 + 消息量（一次全表扫描取轻量列） ═══
        #    DATE(created_at) 输出恒为 'YYYY-MM-DD'，[5:] 切片直接得 'MM-DD'，
        #    避免逐行 datetime.strptime 解析
        cursor.execute(
            "SELECT DATE(created_at) as day, "
            "COALESCE(SUM(CASE WHEN context_usage > 0 THEN context_usage END), 0) as total_tokens, "
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
            label = day_str[5:]
            daily_tokens_map[label] = row["total_tokens"]
            daily_messages_map[label] = row["msgs"]

        # 3. ═══ 回退：context_usage=0 的旧会话用 messages 估算 token ═══
        #    SQL 侧 substr 截断（避免 messages 大字段全量传到 Python，
        #    实测单条可达 13MB）+ LIMIT 兜底（只取最近 100 条足够反映趋势）
        cursor.execute(
            "SELECT DATE(created_at) as day, substr(messages, 1, 50000) as msg "
            "FROM sessions "
            "WHERE created_at >= date('now', '-13 days') "
            "AND project NOT LIKE '__archived__%' "
            "AND (context_usage IS NULL OR context_usage = 0) "
            "AND messages IS NOT NULL AND messages != '' "
            "ORDER BY created_at DESC LIMIT 100"
        )
        for row in cursor.fetchall():
            day_str = row["day"]
            if not day_str:
                continue
            label = day_str[5:]
            msg_data = row["msg"]
            if isinstance(msg_data, (str, bytes)):
                tokens = _fast_estimate_tokens(str(msg_data))
                daily_tokens_map[label] = daily_tokens_map.get(label, 0) + tokens

        # 4. ═══ 组装结果 ═══
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

# 缓存 TTL：db mtime 变化（新会话写入）后 TTL 内不重查，
# 避免用户在欢迎卡片各 tab 间快速切换时反复全表查询；60s 数据新鲜度足够。
_CACHE_TTL_SECONDS = 60.0

_cache: dict = {"key": None, "ts": 0.0, "data": None}


def get_stats() -> dict:
    """带模块级缓存的统计读取（主线程安全、轻量）

    缓存 key = (db 文件 mtime_ns, 当天日期)：
    - key 相同（db 未变化）→ 永远命中
    - key 变化但 TTL 内（60s）→ 用旧数据，避免快速切 tab 反复查询
    - key 变化且超过 TTL → 重查
    - 跨天 → 日期键变化自动重查
    - 无 db → 返回空结果避免反复失败查询
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

    # 1) db 未变化 → 永远命中
    if _cache["key"] == cache_key:
        return _cache["data"]
    # 2) 变化但 TTL 内 → 旧数据兜底（防快速切 tab 反复查询）
    if _cache["data"] is not None and time.monotonic() - _cache["ts"] < _CACHE_TTL_SECONDS:
        return _cache["data"]

    data = _fetch_stats()
    _cache = {"key": cache_key, "ts": time.monotonic(), "data": data}
    return data
