# -*- coding: utf-8 -*-
"""cron-tasks 控制器 — 调度器生命周期 + 信号接线 + UI 刷新（参考 autoloop controller）

- 进程级单例；register_ui 后首个卡片显示 / 按钮点击时 ensure_started
- 调度器常驻（插件加载即随 UI 注册启动，不依赖卡片打开）
- notify → services.notify（InfoBar），jobs_changed → 卡片刷新
- 心跳 5s 推一次：只更新运行中那一行的秒数文字，不重建整表（开关不闪、不重 connect）
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from loguru import logger
from PyQt5.QtCore import QTimer

PLUGIN_ID = "cron-tasks"


class CronTasksController:
    """cron-tasks 插件控制器（进程级单例）"""

    _instance: Optional["CronTasksController"] = None

    @classmethod
    def get_instance(cls) -> "CronTasksController":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        from crontasks_core.scheduler import CronScheduler

        self.scheduler = CronScheduler()
        self._services: Dict[str, Any] = {}
        self._card: Optional[Any] = None
        self._started = False

        # 心跳：5s 一次，仅更新运行中那一行的秒数（不重建整表）
        self._heartbeat = QTimer()
        self._heartbeat.setInterval(5000)
        self._heartbeat.timeout.connect(self._on_heartbeat)
        self._heartbeat_active = False

        # 调度器信号 → 通知 / UI 刷新（默认 AutoConnection：同线程 direct 避免依赖事件循环分发）
        self.scheduler.notify_requested.connect(self._on_notify)
        self.scheduler.job_started.connect(self._on_job_started_for_heartbeat)
        self.scheduler.job_finished.connect(self._on_job_finished_for_heartbeat)
        self.scheduler.jobs_changed.connect(lambda: self._refresh_card())

    def _on_job_started_for_heartbeat(self, _job_id: str):
        """任务开始 → 全量刷一次（确保新建的任务在列表显示）+ 启动心跳"""
        self._refresh_card()
        if not self._heartbeat_active:
            self._heartbeat.start()
            self._heartbeat_active = True

    def _on_job_finished_for_heartbeat(self, *_a):
        """任务结束 → 全量刷一次（更新状态文字）+ 停心跳"""
        self._refresh_card()
        if not self.scheduler.is_running_job():
            self._heartbeat.stop()
            self._heartbeat_active = False

    def _on_heartbeat(self):
        """5 秒节拍：仅更新运行中那一行的秒数文字（不开关 / 不重建）"""
        card = self._card
        if card is None:
            self._heartbeat.stop()
            self._heartbeat_active = False
            return
        try:
            card.update_running_row_elapsed()
        except RuntimeError:
            self._card = None
            self._heartbeat.stop()
            self._heartbeat_active = False
        except Exception as e:
            logger.warning(f"[cron-tasks] heartbeat: {e}")

    # ================================================================
    #  启动 / 停止
    # ================================================================

    def ensure_started(self, ctx: Dict[str, Any] | None = None):
        """单例启动调度器；ctx 提供 services 时刷新缓存（含 main_widget 供模型覆盖）"""
        if ctx:
            services = ctx.get("services")
            if isinstance(services, dict) and services.get("create_engine_session"):
                self._services = services
                self.scheduler.set_services(services)
            mw = ctx.get("main_widget")
            if mw is not None:
                self.scheduler._main_widget = mw
        if not self._started:
            self.scheduler.start()
            self._started = True

    def shutdown_all(self):
        """插件卸载 / 应用退出"""
        try:
            self.scheduler.stop()
        except Exception as e:
            logger.warning(f"[cron-tasks] shutdown: {e}")
        self._heartbeat.stop()
        self._heartbeat_active = False
        self._started = False

    # ================================================================
    #  UI 桥接
    # ================================================================

    def bind_card(self, card):
        """任务中心卡注册（卡片显示时调用）"""
        self._card = card
        try:
            card.destroyed.connect(lambda _=None: self._on_card_destroyed())
        except (TypeError, RuntimeError):
            pass

    def _on_card_destroyed(self):
        self._card = None

    def _refresh_card(self):
        card = self._card
        if card is None:
            return
        try:
            card.refresh_jobs()
        except RuntimeError:
            self._card = None  # C++ 对象已销毁
        except Exception as e:
            logger.warning(f"[cron-tasks] refresh_card: {e}")

    def _on_notify(self, title: str, message: str):
        """通知：services.notify（InfoBar）；缓存空时从 registry 活跃窗口兜底拉"""
        notify = (self._services or {}).get("notify")
        if not callable(notify):
            try:
                from app.plugins.registries.ui_plugin_registry import UIPluginRegistry

                reg = UIPluginRegistry.get_instance()
                provider = reg._resolve_active_window_provider() or reg._context_provider
                if provider is not None:
                    ctx = provider() or {}
                    notify = (ctx.get("services") or {}).get("notify")
            except Exception:
                notify = None
        if callable(notify):
            try:
                notify(title, message)
                return
            except Exception:
                pass
        logger.info(f"[cron-tasks] {title}: {message}")

    # ================================================================
    #  UI 动作入口（卡片调用）
    # ================================================================

    def get_job(self, job_id: str):
        return next((j for j in self.scheduler.get_jobs() if j.id == job_id), None)

    def save_job(self, job) -> str:
        """新建或更新（按 job.id 判重）。返回错误信息（空=成功）"""
        existing = self.get_job(job.id)
        err = self.scheduler.update_job(job) if existing is not None else self.scheduler.add_job(job)
        if not err and existing is None:
            self._on_notify("定时任务", f"✅ 已创建「{job.display_label()}」· {job.schedule_desc()}")
        elif not err:
            self._on_notify("定时任务", f"✅ 已更新「{job.display_label()}」")
        return err

    def delete_job(self, job_id: str):
        label = job_id
        job = self.get_job(job_id)
        if job is not None:
            label = job.display_label()
        if self.scheduler.delete_job(job_id):
            self._on_notify("定时任务", f"🗑 已删除「{label}」")

    def toggle_job(self, job_id: str):
        self.scheduler.toggle_job(job_id)

    def run_now(self, job_id: str):
        job = self.get_job(job_id)
        if job is not None:
            self._on_notify("定时任务", f"▶ 立即执行「{job.display_label()}」")
        self.scheduler.run_now(job_id)

    def stop_job(self, job_id: str):
        job = self.get_job(job_id)
        label = job.display_label() if job is not None else job_id
        if self.scheduler.cancel_job(job_id):
            self._on_notify("定时任务", f"⏹ 正在停止「{label}」…")
        else:
            self._on_notify("定时任务", f"「{label}」未在运行")