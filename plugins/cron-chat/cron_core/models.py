# -*- coding: utf-8 -*-
"""CronChat 任务模型 — CronTask / RunRecord 数据类 + 下次执行时间计算

调度语义（与截图编辑页对齐）：
- schedule_type = "daily"   每天 HH:MM
- schedule_type = "weekly"  每周指定星期几 HH:MM（weekdays: 0=周一 ... 6=周日）
- schedule_type = "interval" 每隔 N 分钟（从启用时刻起算，基于上次执行时间滚动）
- schedule_type = "once"    指定日期时间单次（执行后自动禁用）

生效日期区间（可选）：active_from / active_to（ISO 日期，留空表示不限制）。
"""

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

SCHEDULE_TYPES = ("daily", "weekly", "interval", "once")

TYPE_LABELS = {
    "daily": "每天",
    "weekly": "每周",
    "interval": "按间隔",
    "once": "单次",
}

WEEKDAY_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def now() -> datetime:
    return datetime.now()


def _parse_hhmm(text: str) -> tuple:
    """解析 HH:MM → (hour, minute)；非法回退 09:00"""
    try:
        parts = str(text).strip().split(":")
        h, m = int(parts[0]), int(parts[1])
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except (ValueError, IndexError):
        pass
    return 9, 0


def _parse_date(text: str) -> Optional[datetime]:
    """解析 ISO 日期（YYYY-MM-DD），非法返回 None"""
    try:
        return datetime.strptime(str(text).strip()[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


@dataclass
class CronTask:
    """定时对话任务"""

    name: str = ""
    prompt: str = ""
    schedule_type: str = "daily"  # daily / weekly / interval / once
    time_hhmm: str = "09:00"  # daily / weekly / once 的触发时刻
    weekdays: List[int] = field(default_factory=lambda: [0])  # weekly 生效星期（0=周一）
    interval_minutes: int = 60  # interval 间隔分钟
    once_datetime: str = ""  # once 的 YYYY-MM-DD HH:MM
    active_from: str = ""  # 生效起始日期（可选，YYYY-MM-DD）
    active_to: str = ""  # 生效结束日期（可选）
    use_tools: bool = True  # 是否允许任务中使用工具
    enabled: bool = True
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(default_factory=lambda: now().isoformat(timespec="seconds"))
    next_run_at: str = ""  # 下次执行时间（ISO，调度器维护）
    last_run_at: str = ""  # 上次执行时间（ISO）

    # ── 序列化 ──

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CronTask":
        task = cls()
        for key, value in (data or {}).items():
            if hasattr(task, key):
                setattr(task, key, value)
        if task.schedule_type not in SCHEDULE_TYPES:
            task.schedule_type = "daily"
        return task

    # ── 生效判断 ──

    def in_active_range(self, at: Optional[datetime] = None) -> bool:
        """当前时间是否落在生效日期区间内（留空表示不限制）"""
        at = at or now()
        if self.active_from:
            start = _parse_date(self.active_from)
            if start and at.date() < start.date():
                return False
        if self.active_to:
            end = _parse_date(self.active_to)
            if end and at.date() > end.date():
                return False
        return True

    # ── 下次执行时间计算 ──

    def compute_next_run(self, after: Optional[datetime] = None) -> Optional[datetime]:
        """计算 after 之后的下次执行时间；无下次（单次已过）返回 None"""
        after = after or now()

        if not self.enabled or not self.in_active_range(after):
            return None

        if self.schedule_type == "interval":
            minutes = max(1, int(self.interval_minutes or 60))
            base = self._parse_dt(self.last_run_at) or self._parse_dt(self.created_at) or after
            candidate = base + timedelta(minutes=minutes)
            while candidate <= after:
                candidate += timedelta(minutes=minutes)
            # 生效区间终点检查
            if self.active_to:
                end = _parse_date(self.active_to)
                if end and candidate.date() > end.date():
                    return None
            return candidate

        h, m = _parse_hhmm(self.time_hhmm)

        if self.schedule_type == "once":
            target = self._parse_dt(self.once_datetime)
            if target is None:
                return None
            return target if target > after else None

        if self.schedule_type == "daily":
            candidate = after.replace(hour=h, minute=m, second=0, microsecond=0)
            if candidate <= after:
                candidate += timedelta(days=1)
            return self._clip_to_active_range(candidate)

        if self.schedule_type == "weekly":
            weekdays = [int(w) for w in (self.weekdays or []) if 0 <= int(w) <= 6]
            if not weekdays:
                return None
            for offset in range(0, 15):
                day = (after + timedelta(days=offset)).date()
                if day.weekday() not in weekdays:
                    continue
                candidate = datetime(day.year, day.month, day.day, h, m)
                if candidate > after:
                    return self._clip_to_active_range(candidate)
            return None

        return None

    def _clip_to_active_range(self, candidate: datetime) -> Optional[datetime]:
        if self.active_to:
            end = _parse_date(self.active_to)
            if end and candidate.date() > end.date():
                return None
        return candidate

    @staticmethod
    def _parse_dt(text: str) -> Optional[datetime]:
        """解析 ISO datetime（兼容 YYYY-MM-DD HH:MM 与 ISO 格式）"""
        text = str(text or "").strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
            try:
                return datetime.strptime(text[:19], fmt)
            except ValueError:
                continue
        return None

    # ── 展示 ──

    def schedule_summary(self) -> str:
        """人类可读的频率描述（列表卡展示用）"""
        if self.schedule_type == "daily":
            return f"每天 {self.time_hhmm}"
        if self.schedule_type == "weekly":
            days = "、".join(WEEKDAY_LABELS[w] for w in self.weekdays if 0 <= w <= 6) or "—"
            return f"每周 {days} {self.time_hhmm}"
        if self.schedule_type == "interval":
            return f"每 {self.interval_minutes} 分钟"
        if self.schedule_type == "once":
            return f"单次 {self.once_datetime or '未设置'}"
        return "未设置"


@dataclass
class RunRecord:
    """单次运行记录"""

    task_id: str = ""
    task_name: str = ""
    started_at: str = ""  # ISO
    finished_at: str = ""  # ISO
    status: str = "running"  # running / success / error / timeout / cancelled
    duration_seconds: float = 0.0
    result_text: str = ""  # 响应全文（截断存储）
    error: str = ""

    RESULT_MAX_CHARS = 20000

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunRecord":
        record = cls()
        for key, value in (data or {}).items():
            if hasattr(record, key):
                setattr(record, key, value)
        return record

    @property
    def ok(self) -> bool:
        return self.status == "success"

    @property
    def status_label(self) -> str:
        return {
            "running": "运行中",
            "success": "成功",
            "error": "失败",
            "timeout": "超时",
            "cancelled": "已取消",
        }.get(self.status, self.status)
