# -*- coding: utf-8 -*-
"""CronChat 调度器 — QTimer 轮询 + 到期任务触发

线程模型：调度器活在 UI 线程（QTimer），每 tick 检查到期任务；
到期后由 CronChatController（注入的回调）启动 TaskRunnerWorker 执行。
调度器只负责「何时触发」，不负责「怎么执行」。
"""

from datetime import datetime
from typing import Callable, Dict, Optional

from PyQt5.QtCore import QTimer

from loguru import logger

from .models import CronTask
from .store import CronStore, iso_now


class CronScheduler(QTimer):
    """定时任务调度器（UI 线程 QTimer 轮询）"""

    def __init__(self, on_due: Callable[[CronTask], bool], parent=None):
        """on_due: 到期回调 (task) -> bool（True=已接受执行）"""
        super().__init__(parent)
        self._on_due = on_due
        self._store = CronStore.get_instance()
        self._poll_seconds = 30
        self._ticking = False
        self.setInterval(self._poll_seconds * 1000)
        self.timeout.connect(self._tick)

    # ── 生命周期 ──

    def start_scheduling(self, poll_seconds: int = 30):
        self._poll_seconds = max(10, int(poll_seconds or 30))
        self.setInterval(self._poll_seconds * 1000)
        if not self.isActive():
            self.start()
        self.recompute_all()
        logger.info(f"[cron-chat] 调度器启动（轮询 {self._poll_seconds}s）")

    def stop_scheduling(self):
        if self.isActive():
            self.stop()

    def set_poll_seconds(self, seconds: int):
        self._poll_seconds = max(10, int(seconds or 30))
        self.setInterval(self._poll_seconds * 1000)

    # ── 调度逻辑 ──

    def recompute_all(self):
        """重算全部任务的 next_run_at 并落盘（任务增删改/启动时调用）"""
        tasks = self._store.load_tasks()
        changed = False
        for task in tasks:
            nxt = task.compute_next_run()
            nxt_text = nxt.isoformat(timespec="seconds") if nxt else ""
            if nxt_text != task.next_run_at:
                task.next_run_at = nxt_text
                changed = True
        if changed:
            self._store.save_tasks(tasks)

    def recompute_task(self, task: CronTask):
        task.next_run_at = ""
        nxt = task.compute_next_run()
        if nxt:
            task.next_run_at = nxt.isoformat(timespec="seconds")
        self._store.upsert_task(task)

    def _tick(self):
        """轮询：找出到期任务并触发（防重入）"""
        if self._ticking:
            return
        self._ticking = True
        try:
            self._tick_inner()
        except Exception as e:
            logger.exception(f"[cron-chat] 调度 tick 异常: {e}")
        finally:
            self._ticking = False

    def _tick_inner(self):
        now_dt = datetime.now()
        tasks = self._store.load_tasks()
        for task in tasks:
            if not task.enabled:
                continue
            due_dt = self._parse_iso(task.next_run_at)
            if due_dt is None:
                # 无计划（首次/已过期）：尝试重算一次
                nxt = task.compute_next_run(now_dt)
                if nxt is None:
                    continue
                task.next_run_at = nxt.isoformat(timespec="seconds")
                self._store.upsert_task(task)
                due_dt = nxt
            if due_dt > now_dt:
                continue
            # 到期 → 交给控制器执行（含并发/防重入判断）
            accepted = False
            try:
                accepted = bool(self._on_due(task))
            except Exception as e:
                logger.exception(f"[cron-chat] on_due 回调异常: {e}")
            if accepted:
                # 记录本次执行时间并滚动下次计划
                task.last_run_at = iso_now()
                if task.schedule_type == "once":
                    task.enabled = False  # 单次执行后自动禁用
                nxt = task.compute_next_run()
                task.next_run_at = nxt.isoformat(timespec="seconds") if nxt else ""
                self._store.upsert_task(task)
            else:
                # 未接受（如正在运行）：推迟一个轮询周期，避免每 tick 重试
                from datetime import timedelta

                task.next_run_at = (now_dt + timedelta(seconds=self._poll_seconds)).isoformat(timespec="seconds")
                self._store.upsert_task(task)

    @staticmethod
    def _parse_iso(text: str) -> Optional[datetime]:
        text = str(text or "").strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
