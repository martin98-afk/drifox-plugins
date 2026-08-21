# -*- coding: utf-8 -*-
"""taskboard 数据模型 — Task 任务 + BoardStore 看板持久化

看板数据持久化为当前工作目录下的 .taskboard/board.json：
{
  "auto_mode": false,
  "tasks": [ {task dict}, ... ]
}
done 报告全文另存 .taskboard/reports/<task_id>.md，board.json 仅存摘要引用。
"""

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from taskboard_core.config import (
    BOARD_DIR_NAME,
    BOARD_FILE_NAME,
    REPORTS_DIR_NAME,
    COLUMNS,
)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class Task:
    """看板任务"""

    id: str
    title: str
    detail: str = ""
    status: str = "todo"
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    # 卡片摘要行（该任务最近一次智能体处理的结论）
    last_summary: str = ""
    # 各列处理记录（上下文链：todo 评估结论 → 执行结果 → 审查结论）
    context_log: List[Dict[str, Any]] = field(default_factory=list)
    # 状态流转历史
    history: List[Dict[str, Any]] = field(default_factory=list)
    # 最近一次错误
    error: str = ""

    # ── 运行时态（不持久化）──
    processing: bool = field(default=False, compare=False)
    _stream_preview: str = field(default="", compare=False)   # 处理中流式预览
    _tool_rounds: int = field(default=0, compare=False)        # 本次处理工具调用轮次
    _started_at: float = field(default=0.0, compare=False)     # 本次处理开始时间戳

    @staticmethod
    def create(title: str, detail: str = "", status: str = "todo") -> "Task":
        task = Task(
            id=uuid.uuid4().hex[:12],
            title=title.strip() or "未命名任务",
            detail=detail.strip(),
            status=status if status in COLUMNS else "todo",
        )
        task.history.append({"from": "", "to": task.status, "at": _now(), "by": "user"})
        return task

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "detail": self.detail,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_summary": self.last_summary,
            "context_log": self.context_log,
            "history": self.history,
            "error": self.error,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Task":
        task = Task(
            id=str(d.get("id") or uuid.uuid4().hex[:12]),
            title=str(d.get("title") or "未命名任务"),
            detail=str(d.get("detail") or ""),
            status=d.get("status") or "todo",
            created_at=str(d.get("created_at") or _now()),
            updated_at=str(d.get("updated_at") or _now()),
            last_summary=str(d.get("last_summary") or ""),
            context_log=list(d.get("context_log") or []),
            history=list(d.get("history") or []),
            error=str(d.get("error") or ""),
        )
        if task.status not in COLUMNS:
            task.status = "todo"
        return task

    def append_context(self, column: str, agent: str, summary: str) -> None:
        """追加一条列处理记录"""
        self.context_log.append(
            {"column": column, "agent": agent, "summary": summary, "at": _now()}
        )
        self.last_summary = summary
        self.updated_at = _now()

    def move_to(self, new_status: str, by: str = "user") -> None:
        """状态流转（记录历史）"""
        if new_status == self.status or new_status not in COLUMNS:
            return
        self.history.append({"from": self.status, "to": new_status, "at": _now(), "by": by})
        self.status = new_status
        self.updated_at = _now()


class BoardStore:
    """看板持久化（JSON 文件，工作目录级隔离）"""

    def __init__(self, workdir: str):
        self._workdir = Path(workdir) if workdir else Path.cwd()
        self._board_dir = self._workdir / BOARD_DIR_NAME
        self._board_file = self._board_dir / BOARD_FILE_NAME
        self._lock = threading.Lock()
        self._dirty = False

    @property
    def board_dir(self) -> Path:
        return self._board_dir

    @property
    def reports_dir(self) -> Path:
        return self._board_dir / REPORTS_DIR_NAME

    def load(self) -> Dict[str, Any]:
        """读取看板数据；不存在或损坏时返回初始结构"""
        with self._lock:
            if not self._board_file.exists():
                return {"auto_mode": False, "tasks": []}
            try:
                data = json.loads(self._board_file.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    return {"auto_mode": False, "tasks": []}
                data.setdefault("auto_mode", False)
                data.setdefault("tasks", [])
                return data
            except Exception as e:
                logger.warning(f"[taskboard] board.json 读取失败: {e}")
                return {"auto_mode": False, "tasks": []}

    def save(self, auto_mode: bool, tasks: List[Task]) -> None:
        """写入看板数据（processing 运行时态不入盘）"""
        payload = {
            "auto_mode": bool(auto_mode),
            "tasks": [t.to_dict() for t in tasks],
        }
        with self._lock:
            try:
                self._board_dir.mkdir(parents=True, exist_ok=True)
                self._board_file.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except Exception as e:
                logger.warning(f"[taskboard] board.json 写入失败: {e}")

    # ── done 报告文件 ──

    def report_path(self, task_id: str) -> Path:
        return self.reports_dir / f"{task_id}.md"

    def save_report(self, task_id: str, report: str) -> Optional[Path]:
        """保存 done 报告全文，返回文件路径"""
        if not report or not report.strip():
            return None
        try:
            self.reports_dir.mkdir(parents=True, exist_ok=True)
            path = self.report_path(task_id)
            path.write_text(report, encoding="utf-8")
            return path
        except Exception as e:
            logger.warning(f"[taskboard] 报告保存失败 task={task_id}: {e}")
            return None

    def load_report(self, task_id: str) -> str:
        """读取 done 报告全文；无文件返回空串"""
        path = self.report_path(task_id)
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"[taskboard] 报告读取失败 task={task_id}: {e}")
            return ""
