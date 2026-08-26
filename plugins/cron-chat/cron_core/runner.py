# -*- coding: utf-8 -*-
"""CronChat 任务执行器 — TaskRunnerWorker(QThread)

执行模型（EP3 契约，app/plugins/contracts/engine_session.py）：
- EngineSession 在 UI 线程由 services["create_engine_session"]("cron-chat") 创建
  （ConversationCore/Executor 构建面与 autoloop 同模式），传入 worker
- worker 线程内 session.turn() 同步阻塞执行一轮「带工具自主对话」：
  LLM 可多轮调用工具，完成后返回最终文本
- 结果经 finished_run(dict) 信号回 UI 线程写运行记录 + 通知
"""

from typing import Any, Dict

from PyQt5.QtCore import QThread, pyqtSignal

from loguru import logger

from .models import CronTask, RunRecord
from .store import iso_now

# 任务执行系统提示：约束输出形态（结果将被存档查阅，不追问）
SYSTEM_PROMPT = """你是 DriFox 的定时任务执行器，正在替用户执行一个预设的自动化任务。

规则：
1. 直接执行任务并给出完整结果，不要向用户追问——没人会回答。
2. 需要外部信息或操作时主动使用可用工具完成，不要假设工具不可用。
3. 输出为结构化正文（可含标题/要点/表格），用户会在「运行记录」中查阅。
4. 语言与任务描述一致，默认中文。"""

# 无工具模式追加：纯对话
NO_TOOLS_SUFFIX = "\n\n（本次任务未启用工具，请仅凭已有知识完成。）"


class TaskRunnerWorker(QThread):
    """单任务执行线程 — 一个任务一次执行对应一个实例"""

    started_run = pyqtSignal(str, str)  # task_id, task_name
    finished_run = pyqtSignal(dict)  # RunRecord.to_dict()

    def __init__(self, task: CronTask, session: Any, services: Dict[str, Any], timeout_seconds: float, parent=None):
        super().__init__(parent)
        self._task = task
        self._session = session
        self._services = services or {}
        self._timeout = max(60.0, float(timeout_seconds or 600))
        self._cancelled = False

    def cancel(self):
        """非阻塞取消（UI 关闭/插件卸载时）"""
        self._cancelled = True
        try:
            self._session.cancel()
        except Exception as e:
            logger.warning(f"[cron-chat] cancel 失败: {e}")

    def run(self):
        record = RunRecord(
            task_id=self._task.task_id,
            task_name=self._task.name,
            started_at=iso_now(),
            status="running",
        )
        self.started_run.emit(self._task.task_id, self._task.name)
        logger.info(f"[cron-chat] 任务开始: {self._task.name} ({self._task.task_id})")

        import time

        start = time.monotonic()
        try:
            tools = None
            if self._task.use_tools:
                tools = self._tools_schema()
            system = SYSTEM_PROMPT + (NO_TOOLS_SUFFIX if not self._task.use_tools else "")
            result = self._session.turn(
                system=system,
                user=self._task.prompt,
                tools=tools,
                timeout=self._timeout,
            )
            record.duration_seconds = round(time.monotonic() - start, 1)

            if getattr(result, "ok", False):
                record.status = "success"
                record.result_text = (result.text or "").strip()[: RunRecord.RESULT_MAX_CHARS]
            elif getattr(result, "timed_out", False):
                record.status = "timeout"
                record.error = f"执行超时（上限 {int(self._timeout)} 秒）"
            elif getattr(result, "cancelled", False):
                record.status = "cancelled"
                record.error = "已被取消"
            else:
                record.status = "error"
                record.error = (getattr(result, "error", None) or "未知错误").strip()
        except Exception as e:
            record.duration_seconds = round(time.monotonic() - start, 1)
            record.status = "error"
            record.error = f"{type(e).__name__}: {e}"
            logger.exception(f"[cron-chat] 任务异常: {self._task.name}")

        record.finished_at = iso_now()
        self.finished_run.emit(record.to_dict())
        logger.info(f"[cron-chat] 任务结束: {self._task.name} → {record.status} ({record.duration_seconds}s)")

    def _tools_schema(self):
        """取默认工具集（agent_name 不存在时主程序返回全量工具）"""
        getter = self._services.get("get_tools_schema")
        if not callable(getter):
            return None
        try:
            schema = getter("cron-chat") or []
            return schema or None
        except Exception as e:
            logger.warning(f"[cron-chat] 获取工具集失败，降级为无工具: {e}")
            return None
