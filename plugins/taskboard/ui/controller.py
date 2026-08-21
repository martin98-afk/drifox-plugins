# -*- coding: utf-8 -*-
"""taskboard 控制器 — 任务生命周期 / 并行 worker 管理 / 持久化

进程级单例（与 autoloop controller 同模式），多窗口共享任务数据，
services 取最近绑定窗口的句柄。Qt 信号广播看板变更，看板卡订阅刷新。
"""

import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger
from PyQt5.QtCore import QObject, Qt, pyqtSignal

from taskboard_core.config import (
    BOARD_DIR_NAME,
    COLUMNS,
    COLUMN_META,
    LOGS_DIR_NAME,
    SIGNAL_ADVANCE,
    SIGNAL_DROP,
    SIGNAL_HOLD,
    next_column,
)
from taskboard_core.models import BoardStore, Task
from taskboard_core.worker import TaskWorker

PLUGIN_ID = "taskboard"


class TaskBoardController(QObject):
    """任务看板控制器（进程级单例）"""

    _instance: Optional["TaskBoardController"] = None

    # ── 看板变更广播（看板卡订阅）──
    board_reset = pyqtSignal()               # 全量刷新（加载/清空）
    tasks_changed = pyqtSignal()             # 任务增删/移动
    task_changed = pyqtSignal(str)           # 单任务更新（task_id）
    auto_mode_changed = pyqtSignal(bool)     # 自动/手动模式切换

    @classmethod
    def get_instance(cls) -> "TaskBoardController":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._tasks: Dict[str, Task] = {}          # task_id -> Task（保序 dict）
        self._workers: Dict[str, TaskWorker] = {}  # task_id -> TaskWorker
        self._services: Dict[str, Any] = {}        # 最近绑定的窗口 services
        self._auto_mode: bool = False
        self._store: Optional[BoardStore] = None
        self._lock = threading.Lock()
        self._shutting_down = False

    # ================================================================
    #  绑定与初始化
    # ================================================================

    def bind(self, ctx: Dict[str, Any]) -> None:
        """看板卡显示时上报窗口上下文（services + workdir）"""
        services = ctx.get("services") or {}
        if services:
            self._services = services

        workdir = (ctx.get("project_root") or services.get("get_workdir", lambda: "")() or "").strip()
        if not workdir:
            workdir = str(Path.cwd())
        self._ensure_store(workdir)

    def _ensure_store(self, workdir: str) -> None:
        """工作目录变化时重新加载看板（先停全部 worker）"""
        if self._store is not None and str(self._store.board_dir.parent) == str(workdir):
            return
        if self._workers:
            self.stop_all()
        self._store = BoardStore(workdir)
        data = self._store.load()
        self._auto_mode = bool(data.get("auto_mode", False))
        self._tasks = {}
        for td in data.get("tasks", []):
            try:
                task = Task.from_dict(td)
                self._tasks[task.id] = task
            except Exception as e:
                logger.warning(f"[taskboard] 任务加载失败: {e}")
        self.board_reset.emit()

    @property
    def auto_mode(self) -> bool:
        return self._auto_mode

    def set_auto_mode(self, on: bool) -> None:
        """切换自动/手动模式（自动模式下状态变化即触发处理）"""
        self._auto_mode = bool(on)
        self.auto_mode_changed.emit(self._auto_mode)
        self._persist()

    # ================================================================
    #  任务增删查
    # ================================================================

    def get_tasks(self) -> List[Task]:
        return list(self._tasks.values())

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def is_processing(self, task_id: str) -> bool:
        w = self._workers.get(task_id)
        return bool(w and w.isRunning())

    def processing_count(self) -> int:
        return sum(1 for w in self._workers.values() if w.isRunning())

    def add_task(self, title: str, detail: str = "") -> Optional[Task]:
        """发布新任务到 todo 列；自动模式下立即触发待办列智能体"""
        if not title or not title.strip():
            return None
        task = Task.create(title, detail)
        with self._lock:
            self._tasks[task.id] = task
        self._persist()
        self.tasks_changed.emit()
        self._notify("任务已发布", f"「{task.title}」进入待办列")
        if self._auto_mode:
            self.start_task(task.id, by="auto")
        return task

    def remove_task(self, task_id: str) -> None:
        """删除任务（运行中先停止）"""
        self.stop_task(task_id)
        with self._lock:
            self._tasks.pop(task_id, None)
        self._persist()
        self.tasks_changed.emit()

    def clear_done(self) -> int:
        """清空 done 列任务，返回清除数量"""
        done_ids = [tid for tid, t in self._tasks.items() if t.status == "done"]
        if not done_ids:
            return 0
        with self._lock:
            for tid in done_ids:
                self._tasks.pop(tid, None)
        self._persist()
        self.tasks_changed.emit()
        return len(done_ids)

    # ================================================================
    #  任务移动（按钮 / 拖拽）
    # ================================================================

    def move_task(self, task_id: str, new_status: str, by: str = "user") -> bool:
        """移动任务到指定列

        自动模式语义：任务状态变化后，对应列智能体立即开始处理该任务
        （用户手动模式则等待用户点击开始）。
        """
        task = self._tasks.get(task_id)
        if task is None or new_status not in COLUMNS or new_status == task.status:
            return False
        if self.is_processing(task_id):
            self._notify("任务处理中", "请先停止当前处理再移动")
            return False

        task.move_to(new_status, by=by)
        task.error = ""
        self._persist()
        self.tasks_changed.emit()
        if self._auto_mode and by != "auto":
            self.start_task(task_id, by="auto")
        return True

    # ================================================================
    #  任务处理（开始 / 停止）
    # ================================================================

    def start_task(self, task_id: str, by: str = "user") -> bool:
        """触发该任务当前列绑定的智能体处理"""
        task = self._tasks.get(task_id)
        if task is None:
            return False
        if self.is_processing(task_id):
            self._notify("任务处理中", f"「{task.title}」已在处理")
            return False
        if not self._services:
            self._notify("看板未就绪", "请先打开任务看板卡片再触发处理")
            return False

        column = task.status
        agent = COLUMN_META.get(column, {}).get("agent", "")
        if not agent:
            return False

        log_file = None
        if self._store is not None:
            log_file = self._store.board_dir / LOGS_DIR_NAME / f"{task_id}.md"

        worker = TaskWorker()
        try:
            worker.configure(task=task, column=column, services=self._services, log_file=log_file)
        except Exception as e:
            logger.exception(f"[taskboard] worker 配置失败 task={task_id}")
            self._notify("启动失败", str(e))
            return False

        with self._lock:
            self._workers[task_id] = worker
        task.processing = True
        task.error = ""
        self.task_changed.emit(task_id)
        self._notify(
            "开始处理",
            f"「{task.title}」→ @{agent}（{COLUMN_META.get(column, {}).get('title', column)}）",
        )

        worker.task_log.connect(
            lambda tid, text, w=worker: self._on_worker_log(tid, text), Qt.QueuedConnection
        )
        worker.task_update.connect(
            lambda tid, text: self._on_worker_update(tid, text), Qt.QueuedConnection
        )
        worker.task_error.connect(
            lambda tid, err: self._on_worker_error(tid, err), Qt.QueuedConnection
        )
        worker.task_finished.connect(
            lambda tid, sig, summary, report, w=worker: self._on_worker_finished(tid, sig, summary, report),
            Qt.QueuedConnection,
        )
        worker.finished.connect(lambda w=worker: self._reap_worker(w), Qt.QueuedConnection)
        worker.start()
        return True

    def stop_task(self, task_id: str) -> None:
        """停止运行中的处理（任务保留当前列）"""
        worker = self._workers.get(task_id)
        if worker and worker.isRunning():
            worker.cancel()
            task = self._tasks.get(task_id)
            if task:
                task.processing = False
                task._stream_preview = ""
                self.task_changed.emit(task_id)

    def stop_all(self) -> None:
        for tid in list(self._workers.keys()):
            self.stop_task(tid)

    # ================================================================
    #  worker 回调
    # ================================================================

    def _on_worker_log(self, task_id: str, text: str) -> None:
        task = self._tasks.get(task_id)
        if task is not None:
            self.task_changed.emit(task_id)

    def _on_worker_update(self, task_id: str, preview: str) -> None:
        task = self._tasks.get(task_id)
        if task is not None:
            task._stream_preview = preview  # 运行时态，卡片处理中显示
            self.task_changed.emit(task_id)

    def _on_worker_error(self, task_id: str, error: str) -> None:
        task = self._tasks.get(task_id)
        if task is not None:
            task.error = error
            self.task_changed.emit(task_id)

    def _on_worker_finished(self, task_id: str, signal: str, summary: str, report: str) -> None:
        """处理完成 — 应用去留信号并联动后续"""
        task = self._tasks.get(task_id)
        if task is None:
            return
        task.processing = False
        task._stream_preview = ""
        column = task.status
        agent = COLUMN_META.get(column, {}).get("agent", "")
        task.append_context(column, agent, summary or "处理完成")

        if report and self._store is not None:
            self._store.save_report(task_id, report)

        dropped = False
        if signal == SIGNAL_DROP:
            self._tasks.pop(task_id, None)
            dropped = True
            self._notify("任务已删除", f"「{task.title}」被 @{agent} 判定废弃")
        elif signal == SIGNAL_ADVANCE:
            nxt = next_column(column)
            task.move_to(nxt, by=f"agent:{agent}")
            self._notify("任务推进", f"「{task.title}」→ {COLUMN_META.get(nxt, {}).get('title', nxt)}")

        self._persist()
        self.tasks_changed.emit()

        # 自动模式：推进后的新列继续触发（done 列也触发总结归档）
        if not dropped and signal == SIGNAL_ADVANCE and self._auto_mode and not self._shutting_down:
            self.start_task(task_id, by="auto")

    def _reap_worker(self, worker: TaskWorker) -> None:
        """worker 线程结束后清理引用"""
        tid = worker.task_id
        w = self._workers.get(tid)
        if w is worker:
            self._workers.pop(tid, None)
            task = self._tasks.get(tid)
            if task is not None:
                task.processing = False
                self.task_changed.emit(tid)

    # ================================================================
    #  报告
    # ================================================================

    def get_report(self, task_id: str) -> str:
        if self._store is None:
            return ""
        return self._store.load_report(task_id)

    # ================================================================
    #  持久化与收尾
    # ================================================================

    def _persist(self) -> None:
        if self._store is not None:
            self._store.save(self._auto_mode, list(self._tasks.values()))

    def _notify(self, title: str, message: str) -> None:
        notify = (self._services or {}).get("notify")
        if notify:
            try:
                notify(title, message)
            except Exception:
                pass

    def shutdown(self) -> None:
        """卸载/热重载收尾：停全部 worker、持久化、归零单例"""
        self._shutting_down = True
        self.stop_all()
        # 等待线程收尾（有限等待，避免卡 UI）
        for w in list(self._workers.values()):
            if w.isRunning():
                w.wait(3000)
        self._persist()
        self._workers.clear()
        TaskBoardController._instance = None
        logger.info("[taskboard] controller 已关闭")
