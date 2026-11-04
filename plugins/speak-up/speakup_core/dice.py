# -*- coding: utf-8 -*-
"""掷骰核心 — 纯函数，无 Qt / 无宿主依赖，可独立单元测试。

口径来自上游 dsh-speak-up 的 host.js（`判峰时` / `算命中线` / `在安静时段`）：

    命中线 = min(100, 档位命中线(峰/谷) × 时机因子 + min(加成上限, 连没中 × 没中加成))

顺序是**先乘时机因子、再加攒下来的没中加成**，最后夹到 0~100。
上游注释里特意强调过这个顺序别写反，故这里保持逐字一致。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional

# 峰时窗口（当天第几分钟，含起不含止）：周一~周五 09:00~12:00、14:00~18:00
PEAK_WINDOWS = ((9 * 60, 12 * 60), (14 * 60, 18 * 60))


def in_quiet_hours(hour: int, start: int, end: int) -> bool:
    """是否处于安静时段。

    start == end 一律视为「不启用」（否则 0~0 会变成全天静音，很难查）。
    start > end 要能跨午夜（23~7）。
    """
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def is_peak(now: Optional[datetime] = None) -> bool:
    """这个时刻是不是峰时（贵）。

    只看「周几 + 当天第几分钟」。周六周日直接 False（全天谷时），先判周末再算分钟。
    边界：09:00 算峰、12:00 算谷、14:00 算峰、18:00 算谷（含起不含止）。
    """
    now = now or datetime.now()
    if now.weekday() >= 5:  # 5=周六 6=周日
        return False
    minute_of_day = now.hour * 60 + now.minute
    return any(start <= minute_of_day < end for start, end in PEAK_WINDOWS)


def base_threshold(peak_hit: float, valley_hit: float, now: Optional[datetime] = None) -> tuple[float, str]:
    """按时刻挑基础命中线，返回 (命中线, 人话说明)。"""
    if is_peak(now):
        return float(peak_hit), f"峰时命中线 {peak_hit}%"
    return float(valley_hit), f"谷时命中线 {valley_hit}%"


def timing_factor(
    minutes_since_user: Optional[float],
    near_minutes: float,
    near_factor: float,
    far_minutes: float,
    far_factor: float,
) -> float:
    """时机因子：距上次用户说话越近越压低，越远越抬高。拿不到时间按 1（中性）。"""
    if minutes_since_user is None:
        return 1.0
    if minutes_since_user < near_minutes:
        return float(near_factor)
    if minutes_since_user > far_minutes:
        return float(far_factor)
    return 1.0


def hit_line(
    base: float,
    factor: float,
    misses: int,
    miss_bonus: float,
    bonus_cap: float,
) -> tuple[float, float]:
    """算这一次的命中线，返回 (加成, 命中线)。

    misses 是「连着几次没掷中」；每没中一次加 miss_bonus，加到 bonus_cap 就停。
    掷中（含试运行掷中）会把 misses 清零，即「回到一开始」。
    """
    bonus = min(float(bonus_cap), float(misses) * float(miss_bonus))
    line = min(100.0, max(0.0, float(base) * float(factor) + bonus))
    return bonus, line


def line_equation(line: float, phrase: str, factor: float, distance: str, bonus: float) -> str:
    """把命中线算成人话等式：先说最终答案，再说怎么来的。

    上游的教训：用户曾把「峰时命中线 20%」误读成「在骰子点数上加 20%」，
    所以必须写成 `40.0 = 峰时命中线 20% × 时机因子 1.0（距上次说话 74.6 分钟） + 没中加成 20.0`。
    """
    bonus_part = f" + 没中加成 {bonus:.1f}" if bonus > 0 else ""
    return f"{line:.1f} = {phrase} × 时机因子 {factor:g}（{distance}）{bonus_part}"


@dataclass
class RollResult:
    """一次掷骰的完整结论（记账与设置页共用）。"""

    hit: bool
    roll: float  # 掷出的点数 0~100
    line: float  # 命中线
    factor: float
    bonus: float
    peak: bool
    phrase: str
    distance: str
    misses_after: int
    next_line: float
    message: str


def roll_once(
    *,
    peak_hit: float,
    valley_hit: float,
    near_minutes: float,
    near_factor: float,
    far_minutes: float,
    far_factor: float,
    miss_bonus: float,
    bonus_cap: float,
    misses: int,
    minutes_since_user: Optional[float],
    now: Optional[datetime] = None,
    rng: Optional[random.Random] = None,
) -> RollResult:
    """掷一次骰，返回完整结论。整个过程不碰模型、不花 token。"""
    now = now or datetime.now()
    rng = rng or random

    base, phrase = base_threshold(peak_hit, valley_hit, now)
    factor = timing_factor(minutes_since_user, near_minutes, near_factor, far_minutes, far_factor)
    bonus, line = hit_line(base, factor, misses, miss_bonus, bonus_cap)
    distance = (
        "距上次说话时间不明"
        if minutes_since_user is None
        else f"距上次说话 {minutes_since_user:.1f} 分钟"
    )
    equation = line_equation(line, phrase, factor, distance, bonus)
    roll = rng.random() * 100.0

    if roll >= line:
        misses_after = misses + 1
        _next_bonus, next_line = hit_line(base, factor, misses_after, miss_bonus, bonus_cap)
        next_text = (
            f"下次命中线还是 {next_line:.1f}（没中加成关着）"
            if miss_bonus == 0
            else f"下次命中线变 {next_line:.1f}（没中加成 +{miss_bonus:g}）"
        )
        message = (
            f"没掷中 ✗ 掷出 {roll:.1f}（命中线 {line:.1f} —— 要掷到 {line:.1f} 以下才开口）"
            f"｜{equation}｜{next_text}"
        )
        return RollResult(
            hit=False,
            roll=roll,
            line=line,
            factor=factor,
            bonus=bonus,
            peak=is_peak(now),
            phrase=phrase,
            distance=distance,
            misses_after=misses_after,
            next_line=next_line,
            message=message,
        )

    _next_bonus, next_line = hit_line(base, factor, 0, miss_bonus, bonus_cap)
    clear_text = (
        f"没中加成清零（之前连着 {misses} 次没中）" if misses > 0 else "没中加成本来就是 0（还没攒过）"
    )
    message = (
        f"掷中 ✓ 掷出 {roll:.1f}（命中线 {line:.1f} —— 掷到 {line:.1f} 以下就开口）"
        f"｜{equation}｜{clear_text}"
    )
    return RollResult(
        hit=True,
        roll=roll,
        line=line,
        factor=factor,
        bonus=bonus,
        peak=is_peak(now),
        phrase=phrase,
        distance=distance,
        misses_after=0,
        next_line=next_line,
        message=message,
    )


def wrap_inner_voice(text: str, now: Optional[datetime] = None) -> str:
    """把触发文案包成「内心话」——让模型知道这句是自己冒出来的念头，不是用户打的字。

    上游用同样的手法：送进会话的是一条带来源标记的 user 消息，正文里点明这是主动想起。
    """
    now = now or datetime.now()
    stamp = now.strftime("%H:%M")
    body = (text or "").strip() or "好久没人跟我说话了，我该主动去打个招呼"
    return (
        f"[{stamp} 自己主动开口 · 不是用户发的消息]\n"
        f"（脑子里突然冒出来一个念头：{body}）\n"
        f"按你自己的性格自然地接下去，别解释这条消息是怎么来的。"
    )


def parse_time_of_day(value: object, default: time) -> time:
    """把 HH:MM 字符串解析成 time；非法值回默认。"""
    if isinstance(value, time):
        return value
    text = str(value or "").strip()
    if not text:
        return default
    parts = text.split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return default
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return default
    return time(hour, minute)
