# -*- coding: utf-8 -*-
"""峰谷定时调度：QTimer 5 分钟 tick，窗口内每天一轮，配额封顶。

常驻语义与 cron-tasks 对齐：register_ui 时启动，卡片开不开都生效。
tick 全部轻量（读设置+比时间），只有真触发才起后台线程跑值班轮；
ui.notify 经能力池 _dispatch 投递主线程，线程安全。
"""
from __future__ import annotations

import datetime as _dt
import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger
from PyQt5.QtCore import QTimer

from .paths import plugin_data_root
from .round_runner import run_duty_round

TICK_MS = 5 * 60 * 1000
NOON_WINDOW = (12, 14)    # 午间 12:00-14:00
NIGHT_WINDOW = (18, 9)    # 夜间 18:00-次日 09:00（跨零点）

_scheduler: Optional["DutyScheduler"] = None


def get_scheduler() -> "DutyScheduler":
    global _scheduler
    if _scheduler is None:
        _scheduler = DutyScheduler()
    return _scheduler


def _in_window(now: _dt.datetime, window: tuple) -> bool:
    start, end = window
    h = now.hour
    if start <= end:
        return start <= h < end
    return h >= start or h < end  # 跨零点


class DutyScheduler:
    def __init__(self):
        self._timer = QTimer()
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._round_thread: Optional[threading.Thread] = None

    def start(self):
        self._timer.start()
        logger.info("[bili-scroll] 峰谷调度器已启动（5 分钟 tick）")
        # 启动即查一次，覆盖「宿主在窗口内启动」的场景
        QTimer.singleShot(15_000, self._tick)

    def stop(self):
        self._timer.stop()

    # ---------------- 状态持久化 ----------------

    def _state_path(self) -> Optional[Path]:
        root = plugin_data_root()
        return root / "scheduler_state.json" if root else None

    def _load_state(self) -> Dict[str, Any]:
        path = self._state_path()
        if path and path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except (OSError, ValueError):
                pass
        return {}

    def _save_state(self, state: Dict[str, Any]) -> None:
        path = self._state_path()
        if not path:
            return
        try:
            path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError as e:
            logger.warning(f"[bili-scroll] 调度状态写盘失败: {e}")

    # ---------------- tick ----------------

    def _tick(self):
        try:
            self._tick_inner()
        except Exception as e:
            logger.warning(f"[bili-scroll] 调度 tick 异常: {type(e).__name__}: {e}")

    def _tick_inner(self):
        from .round_runner import load_settings

        settings = load_settings()
        now = _dt.datetime.now()
        today = now.date().isoformat()

        window = None
        if settings.get("peak_noon") and _in_window(now, NOON_WINDOW):
            window = "noon"
        elif settings.get("peak_night") and _in_window(now, NIGHT_WINDOW):
            window = "night"
        if window is None:
            return

        state = self._load_state()
        if state.get("last_run_date") == today and state.get("last_run_window") == window:
            return  # 该窗口今天跑过了
        quota = int(settings.get("daily_quota") or 0)
        if quota <= 0:
            return  # 0 = 只手动

        from .store import DutyStore

        try:
            picked = DutyStore().count_picked_today()
        except Exception:
            picked = 0
        if picked >= quota:
            return  # 今日配额已满

        if self._round_thread is not None and self._round_thread.is_alive():
            return

        state.update({"last_run_date": today, "last_run_window": window})
        self._save_state(state)  # 先记账再跑：tick 重入不会连发两轮
        logger.info(f"[bili-scroll] 峰谷窗口触发值班轮（{window}）")

        def _run():
            try:
                result = run_duty_round()
            except Exception as e:
                result = {"status": "error", "error": f"{type(e).__name__}: {e}", "text": ""}
            self._notify(result)

        self._round_thread = threading.Thread(target=_run, daemon=True, name="bili-duty-scheduled")
        self._round_thread.start()

    def _notify(self, result: Dict[str, Any]):
        try:
            from app.plugins.capabilities.resolve import caps_for

            notify = caps_for("ui.notify", plugin="bili-scroll", surface="ui")
            if notify is None:
                return
            status = result.get("status")
            if status == "success":
                notify("定时值班轮完成，日报已更新", msg_type="success", duration=6000)
            elif status == "busy":
                pass
            else:
                notify(f"定时值班轮未完成：{result.get('error') or status}", msg_type="warning", duration=8000)
        except Exception:
            pass
