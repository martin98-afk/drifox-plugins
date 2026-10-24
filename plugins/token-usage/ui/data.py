# -*- coding: utf-8 -*-
"""数据层 — 从 sessions.messages 解压出真实 API usage，按日聚合

口径（全量求和，用户 2026-10-21 确认）：
- 输入 Token = 每轮 usage.input **原样累加**（与 API 计费口径一致）
- 输出 Token = 每轮 usage.output 之和
- 总 Token = 输入 + 输出
- 请求次数 = 窗口内全部 token_usage 记录条数（每次 API 调用算一次）
- 热力图色阶按当日「总 Token」取

为什么不扣增量（2026-10-21 推翻 10-14 的净占用口径）：DriFox 每轮请求都把
整个上下文重发一遍，全量求和看着像「把同一份上下文重复计几十次」，但服务商
就是按这个数字计费的（实测 prompt 中位数 93K / p90 227K，单会话中位 43 轮）。
增量口径报出的量比账单小两个数量级，用户视角等于「统计器坏了」。

为什么不用 sessions.context_usage：那是本地估算的消息总 token，口径与真实
usage 混在一起算不出输入/输出拆分；token_usage 是 API 返回的精确值。

数据形态：sessions.messages 是 zstd 压缩 blob（4 字节 magic "ZSTD" +
1 字节版本 + frame），见主程序 app/core/store/serde.py。旧数据为裸 JSON
（无 magic），兼容处理。全库解压扫描约 0.6s（476 会话 / 85MB），
必须走后台线程（本插件的 collector），不在主线程调。
"""

import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

from loguru import logger

try:  # Python 3.14+ PEP 784（主程序锁定 3.14）
    from compression import zstd as _zstd
except Exception:  # pragma: no cover - 老解释器无 PEP 784
    _zstd = None

try:
    import orjson as _json
except ImportError:  # pragma: no cover - orjson 非必需
    _json = None

# zstd magic 与版本（对齐主程序 serde.py 格式 A）
_MAGIC_ZSTD = b"ZSTD"
_MAGIC_JSON = b"JSON"

# 候选路径按可信度降序：宿主 API > 环境变量 > 开发态 cwd > 用户目录。
# 只上溯插件文件位置不可靠——plugins/<name>/ui/data.py 上溯五层会落到仓库外的
# 任意目录（如 D:/work/.drifox），可能命中 0 行的空壳库，抢占真实库。
_DEV_CANDIDATES = [
    Path(".drifox") / "sessions.db",  # 开发环境：cwd/.drifox（与宿主一致）
    Path.home() / ".drifox" / "sessions.db",  # 打包后：~/.drifox
    Path.home() / "Library" / "Application Support" / "Drifox" / ".drifox" / "sessions.db",
]

# 探测结果缓存：db 文件运行期不会移动，避免每次采集都 stat 全部候选
_found_db_path: Optional[Path] = None


def _host_db_path() -> Optional[Path]:
    """问宿主要真实数据目录（覆盖 DRIFOX_DATA_DIR / frozen / macOS 四条分支）"""
    env_dir = os.environ.get("DRIFOX_DATA_DIR")
    if env_dir:
        return Path(env_dir) / "sessions.db"
    try:
        from app.utils.utils import get_app_data_dir

        return Path(get_app_data_dir()) / "sessions.db"
    except Exception:
        return None


def _has_sessions_table(db_path: Path) -> bool:
    """候选库有效性：能查到 sessions 表"""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1)
        try:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sessions'"
            ).fetchone()
            return row is not None
        finally:
            conn.close()
    except Exception:
        return False


def find_db() -> Optional[Path]:
    """定位 sessions.db

    顺序：宿主数据目录 → 环境变量 → 开发态 cwd → 用户目录。
    存在同名空壳库时优先选有 sessions 表的那个（空壳库查询结果全 0，
    会让整个页签显示「暂无数据」而真实库有数据）。
    """
    global _found_db_path
    if _found_db_path is not None and _found_db_path.exists():
        return _found_db_path

    candidates = []
    host_path = _host_db_path()
    if host_path is not None:
        candidates.append(host_path)
    candidates.extend(_DEV_CANDIDATES)

    existing = [p for p in candidates if p.exists()]
    for p in existing:
        if _has_sessions_table(p):
            _found_db_path = p
            return p
    _found_db_path = existing[0] if existing else None
    return _found_db_path


def _loads(blob: bytes):
    """JSON 反序列化（orjson 优先，退回标准库）"""
    if _json is not None:
        return _json.loads(blob)
    import json

    return json.loads(blob)


def decode_messages(raw) -> list:
    """解码 messages 字段为消息列表；无法解析返回 []。

    三种格式（对齐主程序 serde.deserialize）：
    - ZSTD + version（当前写入格式）
    - JSON + version（预留）
    - 裸 JSON（旧数据，SQLite TEXT 列会返回 str）
    """
    if not raw:
        return []
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if not isinstance(raw, bytes):
        return []

    if raw.startswith(_MAGIC_ZSTD) or raw.startswith(_MAGIC_JSON):
        if _zstd is None:
            logger.warning("[token-usage] 当前解释器无 compression.zstd，跳过压缩会话")
            return []
        try:
            payload = _zstd.ZstdDecompressor().decompress(raw[5:])
        except Exception as e:
            logger.debug(f"[token-usage] 解压失败: {e}")
            return []
    else:
        payload = raw

    try:
        data = _loads(payload)
    except Exception as e:
        logger.debug(f"[token-usage] JSON 解析失败: {e}")
        return []
    return data if isinstance(data, list) else []


def _int_of(value) -> int:
    """宽松取整（usage 字段可能是 None / 字符串）"""
    try:
        n = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


def collect() -> dict:
    """扫描全库会话，按全量口径聚合每日 usage 序列。

    口径（全量求和，2026-10-21 确认）：
    - 输入 Token = 每轮 usage.input 原样累加（与 API 计费口径一致）
    - 输出 Token = 每轮 usage.output 之和
    - 请求次数 = 带 usage 的消息条数

    Returns:
        dict:
        - daily: Dict[str, [input, output, requests]]，键 'YYYY-MM-DD'
        - sessions: 参与统计的会话数（含 usage 记录的）
        - error: Optional[str]
    """
    result = {"daily": {}, "sessions": 0, "error": None}

    db_path = find_db()
    if db_path is None:
        result["error"] = "未找到会话数据库"
        return result

    conn = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        conn.text_factory = bytes
        rows = conn.execute(
            "SELECT messages FROM sessions "
            "WHERE project NOT LIKE '__archived__%' AND messages IS NOT NULL"
        ).fetchall()
    except Exception as e:
        result["error"] = f"读取数据库失败: {e}"
        logger.error(f"[token-usage] 读取数据库失败: {e}")
        return result
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    daily: Dict[str, list] = {}
    counted_sessions = 0
    for (raw,) in rows:
        messages = decode_messages(raw)
        if not messages:
            continue
        session_requests = 0
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            usage = msg.get("token_usage")
            if not isinstance(usage, dict):
                continue
            day = str(msg.get("timestamp") or "")[:10]
            if len(day) != 10:
                continue
            slot = daily.setdefault(day, [0, 0, 0])
            # 全量口径：每轮 input / output 原样累加，不做会话内去重
            slot[0] += _int_of(usage.get("input"))
            slot[1] += _int_of(usage.get("output"))
            slot[2] += 1  # 请求次数
            session_requests += 1
        if session_requests:
            counted_sessions += 1

    result["daily"] = daily
    result["sessions"] = counted_sessions
    return result


# ── 派生指标 ──────────────────────────────────────────────


def last_n_days(daily: Dict[str, list], days: int, today: Optional[date] = None) -> list:
    """返回最近 N 天的 [(日期串, input, output, requests)]，缺失日补零。

    顺序为从旧到新，便于直接渲染成折线/柱状序列。
    """
    today = today or datetime.now().date()
    out = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        slot = daily.get(d) or (0, 0, 0)
        out.append((d, slot[0], slot[1], slot[2]))
    return out


def sum_window(daily: Dict[str, list], days: int, today: Optional[date] = None) -> dict:
    """最近 N 天汇总：{input, output, total, requests, active_days}"""
    rows = last_n_days(daily, days, today)
    input_sum = sum(r[1] for r in rows)
    output_sum = sum(r[2] for r in rows)
    return {
        "input": input_sum,
        "output": output_sum,
        "total": input_sum + output_sum,
        "requests": sum(r[3] for r in rows),
        "active_days": sum(1 for r in rows if r[3] > 0),
    }


def active_day_totals(daily: Dict[str, list], days: int, today: Optional[date] = None) -> list:
    """最近 N 天的每日总 Token（有请求的日期才返回），从旧到新。

    用于热力图色阶定标（分位数抗单日尖峰）。
    """
    today = today or datetime.now().date()
    out = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        slot = daily.get(d)
        if slot and slot[2] > 0:
            out.append(slot[0] + slot[1])
    return out