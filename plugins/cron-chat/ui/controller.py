# -*- coding: utf-8 -*-
"""CronChat 控制器 — 调度器生命周期 / 任务执行编排 / 卡片绑定

职责：
- 卡片 showEvent 时 bind_card：缓存 ctx（services/main_widget），启动调度器
- 调度到期 on_due：并发检查 → UI 线程创建 EngineSession（EP3）→ TaskRunnerWorker
- 执行结束：写运行记录 → InfoBar 通知 → 刷新卡片
- run_now：手动立即执行（与调度触发同一通道）
- shutdown：插件卸载/退出时停调度器、取消执行中的 worker
"""

import threading
from typing import Any, Dict, Optional

from PyQt5.QtCore import Qt

from loguru import logger

PLUGIN_ID = "cron-chat"


class CronChatController:
    """CronChat 控制器（进程级单例）"""

    _instance: Optional["CronChatController"] = None

    @classmethod
    def get_instance(cls) -> "CronChatController":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._card = None  # 主卡引用（列表/编辑/记录三页）
        self._ctx: Dict[str, Any] = {}  # 最近一次卡片上下文（services 等）
        self._scheduler = None
        self._workers: Dict[str, Any] = {}  # task_id -> TaskRunnerWorker
        self._lock = threading.Lock()
        self._started = False

    # ================================================================
    #  卡片绑定 / 启动
    # ================================================================

    def bind_card(self, card, ctx: Dict[str, Any]):
        """主卡 showEvent 时调用：缓存引用与上下文，首次启动调度器"""
        self._card = card
        if ctx:
            self._ctx = ctx
        if not self._started:
            self._started = True
            poll, timeout, max_records = self._read_config()
            from cron_core.store import CronStore

            CronStore.get_instance().set_max_records(max_records)
            from cron_core.scheduler import CronScheduler

            self._scheduler = CronScheduler(self._on_due)
            self._scheduler.start_scheduling(poll)
            logger.info("[cron-chat] 调度器已随卡片首次绑定启动")

    def _read_config(self):
        """读插件配置：轮询间隔 / 任务超时 / 记录上限"""
        try:
            from app.plugins.managers.plugin_config_store import PluginConfigStore

            store = PluginConfigStore()
            poll = int(store.get(PLUGIN_ID, "poll_interval_seconds") or 30)
            timeout = int(store.get(PLUGIN_ID, "task_timeout_seconds") or 600)
            max_records = int(store.get(PLUGIN_ID, "max_run_records") or 200)
        except Exception as e:
            logger.warning(f"[cron-chat] 配置读取失败，用默认值: {e}")
            poll, timeout, max_records = 30, 600, 200
        return poll, timeout, max_records

    def _services(self) -> Dict[str, Any]:
        return self._ctx.get("services") or {}

    def _notify(self, title: str, message: str):
        services = self._services()
        try:
            services.get("notify", lambda *_: None)(title, message)
        except Exception:
            pass

    # ================================================================
    #  触发执行（调度到期 / 手动运行 共用通道）
    # ================================================================

    def is_task_running(self, task_id: str) -> bool:
        worker = self._workers.get(task_id)
        return bool(worker and worker.isRunning())

    def _on_due(self, task) -> bool:
        """调度到期回调（UI 线程）— 返回 True 表示已接受执行"""
        return self._start_task(task, manual=False)

    def run_now(self, task) -> bool:
        """手动立即执行（UI 线程）"""
        return self._start_task(task, manual=True)

    def _start_task(self, task, manual: bool) -> bool:
        if self.is_task_running(task.task_id):
            if manual:
                self._notify("CronChat", f"任务「{task.name}」正在执行中")
            return False

        services = self._services()
        create_session = services.get("create_engine_session")
        if not callable(create_session):
            logger.warning("[cron-chat] services 无 create_engine_session，无法执行")
            if manual:
                self._notify("CronChat", "对话服务不可用（请先打开一次任务面板）")
            return False

        # EngineSession 在 UI 线程创建（ConversationCore/Executor 构建面）
        try:
            session = create_session(PLUGIN_ID)
        except Exception as e:
            logger.exception(f"[cron-chat] EngineSession 创建失败: {e}")
            if manual:
                self._notify("CronChat", f"会话创建失败: {e}")
            return False

        _, timeout, _ = self._read_config()

        from cron_core.runner import TaskRunnerWorker

        worker = TaskRunnerWorker(task, session, services, timeout)
        worker.started_run.connect(
            lambda tid, name: self._on_run_started(tid, name), Qt.QueuedConnection
        )
        worker.finished_run.connect(
            lambda record: self._on_run_finished(record), Qt.QueuedConnection
        )
        # 线程结束后自清理
        worker.finished.connect(
            lambda tid=task.task_id: self._workers.pop(tid, None), Qt.QueuedConnection
        )
        self._workers[task.task_id] = worker
        worker.start()
        return True

    # ================================================================
    #  执行结果处理
    # ================================================================

    def _on_run_started(self, task_id: str, task_name: str):
        if self._card is not None:
            try:
                self._card.refresh_all()
            except RuntimeError:
                pass

    def _on_run_finished(self, record: Dict[str, Any]):
        """执行结束（UI 线程）：写记录 + 通知 + 刷新卡片"""
        from cron_core.models import RunRecord
        from cron_core.store import CronStore

        store = CronStore.get_instance()
        store.append_run(RunRecord.from_dict(record))

        name = record.get("task_name", "")
        status = record.get("status", "")
        duration = record.get("duration_seconds", 0)
        if status == "success":
            summary = (record.get("result_text") or "").strip().replace("\n", " ")[:60]
            message = f"完成（{duration}s）：{summary}" if summary else f"完成（{duration}s）"
            self._notify("CronChat", f"「{name}」{message}")
        elif status == "timeout":
            self._notify("CronChat", f"「{name}」执行超时")
        elif status == "cancelled":
            logger.info(f"[cron-chat] 任务取消: {name}")
        else:
            self._notify("CronChat", f"「{name}」执行失败：{record.get('error', '')[:80]}")

        if self._card is not None:
            try:
                self._card.refresh_all()
            except RuntimeError:
                pass

        # 会话资源释放
        task_id = record.get("task_id", "")
        worker = self._workers.get(task_id)

        def _cleanup():
            if worker is not None:
                try:
                    worker._session.cleanup()
                except Exception:
                    pass

        from PyQt5.QtCore import QTimer

        QTimer.singleShot(500, _cleanup)

    # ================================================================
    #  卸载 / 退出
    # ================================================================

    def shutdown(self):
        """插件卸载 / 应用退出：停调度器 + 取消执行中的 worker"""
        if self._scheduler is not None:
            self._scheduler.stop_scheduling()
        for task_id, worker in list(self._workers.items()):
            try:
                if worker.isRunning():
                    worker.cancel()
                    worker.wait(3000)
            except Exception as e:
                logger.warning(f"[cron-chat] worker 收尾异常: {e}")
            self._workers.pop(task_id, None)
        logger.info("[cron-chat] 控制器已关闭")
