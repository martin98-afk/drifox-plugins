# -*- coding: utf-8 -*-
"""CronChat 数据存储 — 任务与运行记录的 JSON 持久化

数据目录：<app_data_dir>/plugins/cron-chat/data/
- tasks.json  任务列表
- runs.json   运行记录（按任务分桶，超上限自动清理最旧）

读写均为全量 JSON（任务/记录量级小，无需数据库）；
所有方法线程安全（QThread worker 与 UI 线程共用）。
"""

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from loguru import logger

from .models import CronTask, RunRecord

DATA_DIR_NAME = "cron-chat"


def _data_dir() -> Path:
    from app.utils.utils import get_app_data_dir

    directory = Path(get_app_data_dir()) / "plugins" / DATA_DIR_NAME / "data"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


class CronStore:
    """任务 + 运行记录存储（进程级单例，线程安全）"""

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "CronStore":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._io_lock = threading.Lock()
        self._max_records = 200

    # ── 配置 ──

    def set_max_records(self, count: int):
        self._max_records = max(20, int(count or 200))

    # ── 任务 ──

    def _tasks_file(self) -> Path:
        return _data_dir() / "tasks.json"

    def load_tasks(self) -> List[CronTask]:
        with self._io_lock:
            tasks = self._read_json(self._tasks_file(), [])
        return [CronTask.from_dict(item) for item in tasks]

    def save_tasks(self, tasks: List[CronTask]):
        payload = [task.to_dict() for task in tasks]
        with self._io_lock:
            self._write_json(self._tasks_file(), payload)

    def upsert_task(self, task: CronTask) -> List[CronTask]:
        tasks = self.load_tasks()
        for index, existing in enumerate(tasks):
            if existing.task_id == task.task_id:
                tasks[index] = task
                break
        else:
            tasks.append(task)
        self.save_tasks(tasks)
        return tasks

    def delete_task(self, task_id: str) -> List[CronTask]:
        tasks = [task for task in self.load_tasks() if task.task_id != task_id]
        self.save_tasks(tasks)
        self.delete_runs(task_id)
        return tasks

    def get_task(self, task_id: str):
        for task in self.load_tasks():
            if task.task_id == task_id:
                return task
        return None

    # ── 运行记录 ──

    def _runs_file(self) -> Path:
        return _data_dir() / "runs.json"

    def load_runs(self, task_id: str = "") -> List[RunRecord]:
        with self._io_lock:
            buckets = self._read_json(self._runs_file(), {})
        if task_id:
            rows = buckets.get(task_id, [])
        else:
            rows = [row for rows in buckets.values() for row in rows]
        records = [RunRecord.from_dict(row) for row in rows]
        records.sort(key=lambda record: record.started_at, reverse=True)
        return records

    def append_run(self, record: RunRecord):
        with self._io_lock:
            buckets = self._read_json(self._runs_file(), {})
            rows = buckets.get(record.task_id, [])
            rows.append(record.to_dict())
            # 超上限清理最旧（started_at 升序删头）
            rows.sort(key=lambda row: row.get("started_at", ""))
            if len(rows) > self._max_records:
                rows = rows[-self._max_records:]
            buckets[record.task_id] = rows
            self._write_json(self._runs_file(), buckets)

    def update_run(self, record: RunRecord):
        """按 started_at 定位更新（执行结束回写状态/结果）"""
        with self._io_lock:
            buckets = self._read_json(self._runs_file(), {})
            rows = buckets.get(record.task_id, [])
            for index, row in enumerate(rows):
                if row.get("started_at") == record.started_at:
                    rows[index] = record.to_dict()
                    break
            buckets[record.task_id] = rows
            self._write_json(self._runs_file(), buckets)

    def delete_runs(self, task_id: str):
        with self._io_lock:
            buckets = self._read_json(self._runs_file(), {})
            buckets.pop(task_id, None)
            self._write_json(self._runs_file(), buckets)

    # ── 底层 IO ──

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[cron-chat] 读取 {path.name} 失败: {e}")
        return default

    @staticmethod
    def _write_json(path: Path, payload: Any):
        try:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
        except Exception as e:
            logger.error(f"[cron-chat] 写入 {path.name} 失败: {e}")


def iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")
