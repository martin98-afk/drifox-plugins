# -*- coding: utf-8 -*-
"""定时任务数据模型 + cron 表达式解析 + 下次运行时间计算

对齐 openhanako lib/desk/cron-store.ts 的三种任务类型：
- "at"    一次性任务（schedule = ISO 本地时间字符串）
- "every" 间隔任务（schedule = 间隔分钟数 int）
- "cron"  标准 5 字段 cron 表达式（schedule = "M H Dom Mon Dow"）

cron 解析为内置实现（无第三方依赖）：支持 *、数字、a-b 区间、
*/n 与 a-b/n 步进、逗号组合；dow 字段 7 视为周日 0。
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, List, Optional

WEEKDAY_CN = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]
SCAN_LIMIT_DAYS = 366  # next_run 扫描上限（跨年不匹配 → None）


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ============================================================
#  cron 表达式解析（5 字段：分 时 日 月 周）
# ============================================================


class CronParseError(ValueError):
    """cron 表达式非法"""


def _parse_field(field_expr: str, lo: int, hi: int, is_dow: bool = False) -> List[int]:
    """解析单个字段为升序整数列表

    支持：* | n | a-b | */n | a-b/n | a,b,c 组合；dow 的 7 → 0（周日）
    """
    values = set()
    for chunk in field_expr.split(","):
        chunk = chunk.strip()
        if not chunk:
            raise CronParseError(f"空字段段: {field_expr!r}")
        step = 1
        base = chunk
        if "/" in chunk:
            base, step_s = chunk.split("/", 1)
            try:
                step = int(step_s)
            except ValueError:
                raise CronParseError(f"非法步进: {chunk!r}")
            if step <= 0:
                raise CronParseError(f"步进必须为正整数: {chunk!r}")
        if base in ("*", ""):
            start, end = lo, hi
        elif "-" in base:
            a, _, b = base.partition("-")
            try:
                start, end = int(a), int(b)
            except ValueError:
                raise CronParseError(f"非法区间: {chunk!r}")
        else:
            try:
                start = int(base)
            except ValueError:
                raise CronParseError(f"非法数字: {chunk!r}")
            end = start if "/" not in chunk else hi  # POSIX: "5/15" = 5..hi/15
        # dow: 0-7，其中 7 等价 0（周日）
        eff_hi = 7 if is_dow else hi
        if start < lo or end > eff_hi or start > end:
            raise CronParseError(f"字段越界: {chunk!r}（有效 {lo}-{eff_hi}）")
        if is_dow:
            if start == 7:
                start = 0
            if end == 7:
                end = 0
                if start > 0:
                    # 0-7 / n-7 跨越周日：补 0 后正常走区间
                    values.add(0)
                    end = 6
        values.update(range(start, end + 1, step))
    if not values:
        raise CronParseError(f"字段无有效值: {field_expr!r}")
    return sorted(values)


class CronExpr:
    """5 字段 cron 表达式（分 时 日 月 周）"""

    __slots__ = ("minutes", "hours", "doms", "months", "dows", "_dom_any", "_dow_any")

    def __init__(self, expr: str):
        parts = str(expr).split()
        if len(parts) != 5:
            raise CronParseError(f"cron 表达式需 5 个字段（分 时 日 月 周）: {expr!r}")
        self.minutes = _parse_field(parts[0], 0, 59)
        self.hours = _parse_field(parts[1], 0, 23)
        self.doms = _parse_field(parts[2], 1, 31)
        self.months = _parse_field(parts[3], 1, 12)
        # cron dow（周日=0 … 周六=6）→ Python weekday()（周一=0 … 周日=6）
        self.dows = [6 if d == 0 else d - 1 for d in _parse_field(parts[4], 0, 6, is_dow=True)]
        # POSIX 语义：dom 与 dow 同时受限 → 任一匹配即可（OR）；其中一个为 * → AND
        self._dom_any = parts[2] == "*"
        self._dow_any = parts[4] == "*"

    def _day_match(self, t: datetime) -> bool:
        dom_ok = t.day in self.doms
        dow_ok = t.weekday() in self.dows  # Python: 周一=0 … 周日=6
        if self._dom_any and self._dow_any:
            return True
        if self._dom_any:
            return dow_ok
        if self._dow_any:
            return dom_ok
        return dom_ok or dow_ok

    def next_run(self, after: Optional[datetime] = None) -> Optional[datetime]:
        """计算 after（不含）之后的下一次运行时刻，本地时间、秒归零

        逐级跳跃推进（月 → 天 → 时 → 分），366 天内无匹配返回 None。
        """
        t = (after or datetime.now()).replace(second=0, microsecond=0) + timedelta(minutes=1)
        limit = (after or datetime.now()) + timedelta(days=SCAN_LIMIT_DAYS)
        min_minutes = self.minutes[0]
        while t <= limit:
            if t.month not in self.months:
                # 跳到下月 1 日 00:00
                y, m = (t.year + 1, 1) if t.month == 12 else (t.year, t.month + 1)
                t = t.replace(year=y, month=m, day=1, hour=0, minute=0)
                continue
            if not self._day_match(t):
                t = (t + timedelta(days=1)).replace(hour=0, minute=0)
                continue
            if t.hour not in self.hours:
                nxt_h = next((h for h in self.hours if h > t.hour), None)
                if nxt_h is not None:
                    t = t.replace(hour=nxt_h, minute=min_minutes)
                else:
                    t = (t + timedelta(days=1)).replace(hour=0, minute=0)
                continue
            if t.minute not in self.minutes:
                nxt_m = next((m for m in self.minutes if m > t.minute), None)
                if nxt_m is not None:
                    t = t.replace(minute=nxt_m)
                else:
                    # 本小时分钟耗尽：下一可用小时仍匹配则跳该小时首个分钟
                    nxt_h = next((h for h in self.hours if h > t.hour), None)
                    if nxt_h is not None:
                        t = t.replace(hour=nxt_h, minute=self.minutes[0])
                    else:
                        t = (t + timedelta(days=1)).replace(hour=0, minute=0)
                continue
            return t
        return None


def cron_to_human(expr: str) -> str:
    """cron 表达式 → 中文摘要（常见形态友好化，其余原样展示）"""
    try:
        m, h, dom, mon, dow = str(expr).split()
    except ValueError:
        return f"Cron: {expr}"
    if mon == "*":
        if dom == "*" and dow == "*" and m.isdigit() and h.isdigit():
            return f"每天 {int(h):02d}:{int(m):02d}"
        if dom == "*" and dow.isdigit() and m.isdigit() and h.isdigit():
            wd = WEEKDAY_CN[int(dow) % 7]
            return f"每{wd} {int(h):02d}:{int(m):02d}"
        if dow == "*" and dom.isdigit() and m.isdigit() and h.isdigit():
            return f"每月 {dom} 日 {int(h):02d}:{int(m):02d}"
        if dom == "*" and dow == "*" and h == "*" and m.startswith("*/") and m[2:].isdigit():
            return f"每 {m[2:]} 分钟"
        if dom == "*" and dow == "*" and m == "0" and h.startswith("*/") and h[2:].isdigit():
            return f"每 {h[2:]} 小时"
    return f"Cron: {expr}"


# ============================================================
#  任务模型
# ============================================================

JOB_TYPES = ("at", "every", "cron")
MIN_EVERY_MINUTES = 1
MAX_EVERY_MINUTES = 60 * 24 * 365


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


@dataclass
class CronJob:
    """一条定时任务（字段对齐 openhanako CronJob + 本地化扩展）"""

    id: str = ""
    type: str = "cron"  # at / every / cron
    schedule: Any = ""  # at=ISO时间 every=int分钟 cron=表达式
    label: str = ""
    prompt: str = ""
    agent: str = ""  # 执行智能体名；空 = 跟随主程序默认
    model_key: str = ""  # 执行模型（主程序 provider 配置名）；空 = 跟随当前会话模型
    workdir: str = ""  # 执行工作目录；空 = 当前工作目录
    enabled: bool = True
    created_at: str = field(default_factory=now_iso)
    next_run_at: str = ""  # ISO 本地时间；空 = 待计算/已失效
    last_run_at: str = ""
    last_status: str = ""  # success / error / cancelled / timeout / running
    last_error: str = ""
    run_count: int = 0

    # ---------- 序列化 ----------

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "schedule": self.schedule,
            "label": self.label,
            "prompt": self.prompt,
            "agent": self.agent,
            "modelKey": self.model_key,
            "workdir": self.workdir,
            "enabled": self.enabled,
            "createdAt": self.created_at,
            "nextRunAt": self.next_run_at,
            "lastRunAt": self.last_run_at,
            "lastStatus": self.last_status,
            "lastError": self.last_error,
            "runCount": self.run_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CronJob":
        job = cls()
        job.id = str(data.get("id") or "")
        t = str(data.get("type") or "cron").lower()
        job.type = t if t in JOB_TYPES else "cron"
        job.schedule = data.get("schedule", "")
        if job.type == "every":
            try:
                job.schedule = int(job.schedule)
            except (ValueError, TypeError):
                job.schedule = 60
        job.label = str(data.get("label") or "")
        job.prompt = str(data.get("prompt") or "")
        job.agent = str(data.get("agent") or "")
        job.model_key = str(data.get("modelKey") or "")
        job.workdir = str(data.get("workdir") or "")
        job.enabled = bool(data.get("enabled", True))
        job.created_at = str(data.get("createdAt") or "")
        job.next_run_at = str(data.get("nextRunAt") or "")
        job.last_run_at = str(data.get("lastRunAt") or "")
        job.last_status = str(data.get("lastStatus") or "")
        job.last_error = str(data.get("lastError") or "")
        try:
            job.run_count = int(data.get("runCount") or 0)
        except (ValueError, TypeError):
            job.run_count = 0
        return job

    # ---------- 调度计算 ----------

    def validate(self) -> str:
        """校验任务可执行性，返回错误信息（空 = 合法）"""
        if not self.id:
            return "任务缺少 id"
        if self.type not in JOB_TYPES:
            return f"未知任务类型: {self.type}"
        if not str(self.prompt or "").strip():
            return "任务提示词（prompt）不能为空"
        if self.type == "at":
            if _parse_iso(self.schedule) is None:
                return f"无效的一次性时间: {self.schedule!r}"
        elif self.type == "every":
            try:
                mins = int(self.schedule)
            except (ValueError, TypeError):
                return f"无效的间隔: {self.schedule!r}"
            if not (MIN_EVERY_MINUTES <= mins <= MAX_EVERY_MINUTES):
                return f"间隔需在 {MIN_EVERY_MINUTES}-{MAX_EVERY_MINUTES} 分钟内"
        else:
            try:
                CronExpr(str(self.schedule))
            except CronParseError as e:
                return str(e)
        return ""

    def next_run(self, after: Optional[datetime] = None) -> Optional[datetime]:
        """计算下次运行时刻；单次任务已过期返回 None"""
        base = after or datetime.now()
        if self.type == "at":
            t = _parse_iso(self.schedule)
            return t if (t and t > base) else None
        if self.type == "every":
            return base.replace(second=0, microsecond=0) + timedelta(minutes=int(self.schedule))
        try:
            return CronExpr(str(self.schedule)).next_run(base)
        except CronParseError:
            return None

    def recompute_next_run(self, after: Optional[datetime] = None) -> bool:
        """重算并写入 next_run_at。返回 False = 该任务不会再触发（at 已过期 / 表达式无解）"""
        nxt = self.next_run(after)
        if nxt is None:
            self.next_run_at = ""
            return False
        self.next_run_at = nxt.isoformat(timespec="seconds")
        return True

    def next_run_dt(self) -> Optional[datetime]:
        return _parse_iso(self.next_run_at) if self.next_run_at else None

    # ---------- 展示 ----------

    def display_label(self) -> str:
        label = (self.label or "").strip()
        if label:
            return label
        head = (self.prompt or "").strip().splitlines()
        return head[0][:30] if head else "(未命名)"

    def schedule_desc(self) -> str:
        """调度人话描述"""
        if self.type == "at":
            return f"单次 · {self.schedule}"
        if self.type == "every":
            mins = int(self.schedule)
            if mins % 1440 == 0:
                return f"每 {mins // 1440} 天"
            if mins % 60 == 0:
                return f"每 {mins // 60} 小时"
            return f"每 {mins} 分钟"
        return cron_to_human(str(self.schedule))
