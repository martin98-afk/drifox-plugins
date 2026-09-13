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
from PySide6.QtCore import QTimer

PLUGIN_ID = "cron-tasks"

# 单例锚点：挂在 sys 模块上，跨插件模块重载存活。
# 热重载会清 sys.modules["ui_plugin_cron_tasks.*"] 并生成新一代类对象；
# 若单例只存类属性（cls._instance），新一代会另建实例，上一代的 QTimer/调度器
# 在进程内再无任何可达路径（unload_ui 也只对新模块可见）。实测（2026-09-11）：
# 一次热重载后进程内并存 3 套调度器，状态错位 + 任务卡死后只能重启软件。
_SINGLETON_ANCHOR = "_drifox_cron_tasks_controller"


def _read_anchor():
    import sys

    return getattr(sys, _SINGLETON_ANCHOR, None)


def _write_anchor(inst):
    import sys

    if inst is None:
        try:
            delattr(sys, _SINGLETON_ANCHOR)
        except AttributeError:
            pass
    else:
        setattr(sys, _SINGLETON_ANCHOR, inst)


def _silence_stale(obj) -> bool:
    """快速静默一个遗留 controller 实例（不阻塞）

    只做两件事：停掉仍在 tick 的 QTimer（调度器 tick + 心跳）、异步下发
    executor 取消。不走完整 shutdown_all——遗留实例的 executor 可能卡死，
    等它收尾会把加载路径堵住。
    """
    touched = False
    try:
        sched = getattr(obj, "scheduler", None)
        if sched is not None:
            timer = getattr(sched, "_timer", None)
            if timer is not None and timer.isActive():
                timer.stop()
                touched = True
            ex = getattr(sched, "_executor", None)
            if ex is not None and ex.isRunning():
                cancel = getattr(ex, "cancel", None)
                if callable(cancel):
                    cancel()  # 内部异步下发，立即返回
    except Exception:
        pass
    try:
        hb = getattr(obj, "_heartbeat", None)
        if hb is not None and hb.isActive():
            hb.stop()
            touched = True
    except Exception:
        pass
    return touched


def _sweep_stale_generations(keep, exclude=None) -> int:
    """清扫进程内其他世代的 controller 实例（热重载遗留）

    旧版本单例存类属性（cls._instance）不写锚点，热重载后既无锚点也无模块
    入口可寻，只能按类名从 gc 里找。仅在接棒时执行一次，代价远低于多套
    调度器并存（共写同一份 jobs.json、串行锁失效、状态错位）。
    """
    import gc

    killed = 0
    for obj in gc.get_objects():
        try:
            if obj is keep or obj is exclude or type(obj).__name__ != "CronTasksController":
                continue
        except Exception:
            continue
        if _silence_stale(obj):
            killed += 1
    return killed


class CronTasksController:
    """cron-tasks 插件控制器（进程级单例，锚定 sys 模块跨热重载存活）"""

    @classmethod
    def get_instance(cls) -> "CronTasksController":
        inst = _read_anchor()
        if inst is None:
            inst = cls()
            _write_anchor(inst)
        return inst

    @classmethod
    def takeover(cls) -> "CronTasksController":
        """新一代接棒：停掉上一代实例并新建当前代实例（register_ui 专用）

        热重载后上一代实例只被旧类引用、unload_ui 又不可达，本方法是进程内
        唯一还够得着它的入口。漏停会留下仍在 tick 的 QTimer 与可能运行中的
        executor，多套调度器共写同一份 jobs.json。
        """
        old = _read_anchor()
        if old is not None:
            stopped = False
            try:
                old.shutdown_all()
                stopped = True
                logger.info("[cron-tasks] 热重载接棒：上一代调度器已停止")
            except Exception as e:
                logger.warning(f"[cron-tasks] 上一代实例停止失败: {e}")
            if not stopped:
                # 兜底：shutdown_all 缺失（上一代代码无此方法）或中途异常时，
                # 直接停调度器与心跳，确保旧 QTimer 一定不再 tick
                try:
                    sched = getattr(old, "scheduler", None)
                    if sched is not None:
                        sched.stop()
                except Exception:
                    pass
                try:
                    hb = getattr(old, "_heartbeat", None)
                    if hb is not None:
                        hb.stop()
                except Exception:
                    pass
            _write_anchor(None)
        inst = cls()
        _write_anchor(inst)
        # 清扫其他世代：旧版本单例存类属性、不写锚点，锚点路径够不着它们。
        # 已漏多套实例的进程里，这一步能把多余调度器静默，无需重启软件。
        try:
            killed = _sweep_stale_generations(inst, exclude=old)
            if killed:
                logger.info(f"[cron-tasks] 热重载接棒：已静默 {killed} 个遗留实例")
        except Exception as e:
            logger.warning(f"[cron-tasks] 遗留实例清扫失败: {e}")
        return inst

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
        """任务结束 → 停心跳（刷新交给紧随其后的 jobs_changed，避免同帧双刷整表）"""
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