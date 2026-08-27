# -*- coding: utf-8 -*-
"""定时任务存储 — jobs.json + runs/<jobId>.jsonl（参考 openhanako 存储布局）

- jobs.json：任务列表（原子写）
- runs/<job_id>.jsonl：运行历史（追加写，每行一条 {ts,status,durationMs,error,responseHead,responseText}）

线程安全：QMutex 保护（调度器在主线程 tick，历史记录读写在 UI 线程，
但为防御热重载/未来多线程访问仍统一加锁）。
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import List, Optional

from .models import CronJob

RUNS_KEEP_PER_JOB = 30  # 每任务历史保留条数（现含响应全文，append 后裁剪）


def default_store_dir() -> Path:
    """默认存储目录：<app_data>/plugins/cron-tasks/"""
    try:
        from app.utils.utils import get_app_data_dir

        return Path(get_app_data_dir()) / "plugins" / "cron-tasks"
    except Exception:
        return Path(".drifox") / "plugins" / "cron-tasks"


class CronStore:
    """定时任务持久化仓库"""

    def __init__(self, base_dir: Optional[Path] = None):
        self._base = Path(base_dir) if base_dir else default_store_dir()
        self._jobs_path = self._base / "jobs.json"
        self._runs_dir = self._base / "runs"
        self._lock = threading.RLock()

    # ---------- 任务列表 ----------

    def load_jobs(self) -> List[CronJob]:
        """读取全部任务（损坏/缺失返回空列表，不抛异常）"""
        with self._lock:
            try:
                raw = json.loads(self._jobs_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return []
            jobs_raw = raw.get("jobs") if isinstance(raw, dict) else raw
            if not isinstance(jobs_raw, list):
                return []
            return [CronJob.from_dict(item) for item in jobs_raw if isinstance(item, dict)]

    def save_jobs(self, jobs: List[CronJob]) -> bool:
        """保存任务列表（原子写：临时文件 + replace）"""
        data = {"version": 1, "jobs": [job.to_dict() for job in jobs]}
        with self._lock:
            try:
                self._base.mkdir(parents=True, exist_ok=True)
                tmp = self._jobs_path.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                os.replace(tmp, self._jobs_path)
                return True
            except OSError:
                return False

    # ---------- 运行历史 ----------

    def _run_path(self, job_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in job_id)
        return self._runs_dir / f"{safe}.jsonl"

    def append_run(self, job_id: str, record: dict) -> None:
        """追加一条运行记录并裁剪至保留上限"""
        with self._lock:
            try:
                self._runs_dir.mkdir(parents=True, exist_ok=True)
                path = self._run_path(job_id)
                lines = []
                if path.exists():
                    lines = [
                        ln
                        for ln in path.read_text(encoding="utf-8").splitlines()
                        if ln.strip()
                    ]
                lines.append(json.dumps(record, ensure_ascii=False))
                lines = lines[-RUNS_KEEP_PER_JOB:]
                tmp = path.with_suffix(".jsonl.tmp")
                tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
                os.replace(tmp, path)
            except OSError:
                pass  # 历史写失败不阻断调度主流程

    def load_runs(self, job_id: str, limit: int = 20) -> List[dict]:
        """读取运行历史（倒序：最新在前）"""
        with self._lock:
            path = self._run_path(job_id)
            try:
                lines = [
                    ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()
                ]
            except OSError:
                return []
            records = []
            for ln in lines[-limit:]:
                try:
                    records.append(json.loads(ln))
                except ValueError:
                    continue
            records.reverse()
            return records
