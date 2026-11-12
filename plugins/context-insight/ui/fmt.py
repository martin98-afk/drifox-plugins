# -*- coding: utf-8 -*-
"""数字 / 时间 / 金额格式化。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional


def fmt_int(value: Optional[float]) -> str:
    try:
        n = int(value or 0)
    except (TypeError, ValueError):
        return "0"
    return f"{n:,}"


def fmt_k(value: Optional[float]) -> str:
    try:
        n = float(value or 0)
    except (TypeError, ValueError):
        return "0"
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1_000_000_000:
        v = n / 1_000_000_000
        return f"{sign}{v:.1f}B".replace(".0B", "B")
    if n >= 1_000_000:
        v = n / 1_000_000
        return f"{sign}{v:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        v = n / 1_000
        return f"{sign}{v:.1f}k".replace(".0k", "k")
    return f"{sign}{int(n)}"


def fmt_cost(value: Optional[float], known: bool = True) -> str:
    try:
        n = float(value or 0)
    except (TypeError, ValueError):
        n = 0.0
    if not known and n <= 0:
        return "—"
    if n >= 100:
        return f"${n:,.0f}"
    if n >= 1:
        return f"${n:,.2f}"
    if n >= 0.01:
        return f"${n:.3f}"
    if n > 0:
        return f"${n:.4f}"
    return "$0"


def fmt_pct(value: Optional[float], digits: int = 1) -> str:
    try:
        n = float(value or 0)
    except (TypeError, ValueError):
        n = 0.0
    return f"{n:.{digits}f}%"


def fmt_duration(ms: Optional[float]) -> str:
    try:
        value = float(ms or 0)
    except (TypeError, ValueError):
        return "0s"
    if value <= 0:
        return "0s"
    if value < 1000:
        return f"{int(value)}ms"
    seconds = value / 1000.0
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = seconds / 60.0
    if minutes < 60:
        return f"{minutes:.1f}m"
    return f"{minutes / 60.0:.1f}h"


def fmt_ts(value: str, with_date: bool = True) -> str:
    text = str(value or "")
    if len(text) >= 16:
        return text[5:16] if with_date else text[11:16]
    return text


def fmt_date(value: str) -> str:
    text = str(value or "")
    return text[5:10] if len(text) >= 10 else text


def day_list(days: int, today: Optional[datetime] = None) -> list[str]:
    base = (today or datetime.now()).date()
    return [(base - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]


def parse_ts(value: str) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None
