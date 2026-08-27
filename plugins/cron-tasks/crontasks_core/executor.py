# -*- coding: utf-8 -*-
"""定时任务执行器 — 后台线程经 EngineSession 驱动一轮对话执行任务 prompt

线程模型（EP3 契约）：turn() 阻塞直至完成/超时/取消。
已知主程序实现风险：turn() 内部 threading.Event.wait(timeout) 为单次长阻塞，
取消（cancel_worker 只设标志）不保证唤醒 event —— 极端场景要等满超时，
导致串行锁长期卡死（无法停、后续任务全被挡）。

本执行器的对策：
- turn() 挪到 daemon 工作线程执行；QThread 主体只做 200ms 轮询 done 事件
- 手动取消：cancel 标志 → 唤醒 session.cancel() → 最多再等 3s，
  仍未返回则放弃等待直接收尾（daemon 线程后台自灭，随 turn 超时/完成退出）
- 收尾结果存 _last_result（热重载 stop() 手动收尾消费，_done_keys 去重）
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from loguru import logger
from PyQt5.QtCore import QThread, pyqtSignal

from .models import CronJob

EXECUTION_TIMEOUT_SECONDS = 20 * 60  # 单次任务执行超时（对齐 openhanako 20min）
RESPONSE_HEAD_CHARS = 200  # 通知/列表用的响应摘要长度
CANCEL_GRACE_SECONDS = 3.0  # 取消后等 turn 线程返回的宽限期


def _count_tool_calls(messages: List[Dict[str, Any]]) -> int:
    """统计消息流中的工具调用次数"""
    count = 0
    for msg in messages or []:
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list):
            count += len(tool_calls)
    return count


class CronExecutor(QThread):
    """单次任务执行线程

    完成后发射 result dict：
    {job_id, status, error, response_text, head, duration_ms, tool_calls}
    status: success / error / cancelled / timeout
    """

    finished_with_result = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._job: Optional[CronJob] = None
        self._services: Optional[Dict[str, Any]] = None
        self._system_prompt: str = ""
        self._tools: Optional[List[Dict]] = None
        self._model_override: Optional[Dict[str, Any]] = None
        self._session: Any = None
        self._cancelled = False
        self._last_result: Optional[dict] = None  # run() 结束时保存（停止收尾用）

    def configure(
        self,
        job: CronJob,
        services: Dict[str, Any],
        system_prompt: str = "",
        tools: Optional[List[Dict]] = None,
        model_config_override: Optional[Dict[str, Any]] = None,
    ):
        self._job = job
        self._services = services
        self._system_prompt = system_prompt
        self._tools = tools
        self._model_override = model_config_override

    def cancel(self):
        """非阻塞取消：置标志 + 唤醒 session.cancel()"""
        self._cancelled = True
        session = self._session
        if session is not None:
            try:
                session.cancel()
            except RuntimeError:
                pass  # C++ 对象已销毁

    # ---------------------------------------------------------------

    def run(self):  # noqa: C901
        job = self._job
        started = time.monotonic()
        if job is None or not self._services:
            self._emit({"job_id": "", "status": "error", "error": "executor 未配置"})
            return

        holder: Dict[str, Any] = {}
        done = threading.Event()

        def _turn_worker():
            """daemon 工作线程：跑 session.turn()（其内部 wait 可能永不醒）"""
            try:
                create_session = self._services.get("create_engine_session")
                if not callable(create_session):
                    holder["error"] = "主程序未提供 create_engine_session 服务"
                    return
                session = (
                    create_session("cron-tasks", model_config_override=self._model_override)
                    if self._model_override
                    else create_session("cron-tasks")
                )
                if self._cancelled:
                    holder["cancelled"] = True
                    return
                self._session = session
                result = session.turn(
                    system=(self._system_prompt or None),
                    user=job.prompt,
                    tools=self._tools or [],
                    timeout=EXECUTION_TIMEOUT_SECONDS,
                )
                if getattr(result, "cancelled", False) or self._cancelled:
                    holder["cancelled"] = True
                elif getattr(result, "timed_out", False):
                    holder["timeout"] = f"执行超时（>{EXECUTION_TIMEOUT_SECONDS // 60} 分钟）"
                else:
                    err = getattr(result, "error", None)
                    if err:
                        holder["error"] = str(err)
                    else:
                        holder["text"] = getattr(result, "text", "") or ""
                        holder["messages"] = getattr(result, "messages", None)
            except Exception as e:  # 顶层异常屏障：QThread 静默死亡比报错更糟
                logger.exception("[cron-tasks] turn 线程异常")
                holder["error"] = f"{type(e).__name__}: {e}"
            finally:
                done.set()

        t = threading.Thread(target=_turn_worker, daemon=True, name="cron-turn")
        t.start()

        # QThread 主体：轮询等待（可随时被取消打断）
        while not done.wait(0.2):
            if self._cancelled:
                # 唤醒 session 取消，再给宽限期
                self.cancel()
                if done.wait(CANCEL_GRACE_SECONDS):
                    break
                # turn 仍未返回（wait 卡死场景）：放弃等待直接收尾，
                # daemon 线程后台自灭（session.cancel 已尽力下发）
                duration_ms = int((time.monotonic() - started) * 1000)
                logger.warning("[cron-tasks] turn 未响应取消，放弃等待（后台线程自灭）")
                self._emit(
                    {
                        "job_id": job.id,
                        "status": "cancelled",
                        "error": "已手动停止",
                        "response_text": "",
                        "head": "",
                        "duration_ms": duration_ms,
                        "tool_calls": 0,
                    }
                )
                return

        # 正常返回路径
        duration_ms = int((time.monotonic() - started) * 1000)
        result = {
            "job_id": job.id,
            "status": "success",
            "error": "",
            "response_text": "",
            "head": "",
            "duration_ms": duration_ms,
            "tool_calls": _count_tool_calls(holder.get("messages")),
        }
        if "cancelled" in holder:
            result["status"] = "cancelled"
            result["error"] = "已取消"
        elif "timeout" in holder:
            result["status"] = "timeout"
            result["error"] = holder["timeout"]
        elif "error" in holder:
            result["status"] = "error"
            result["error"] = holder["error"]
        else:
            result["response_text"] = str(holder.get("text") or "")
            result["head"] = " ".join(result["response_text"].split())[:RESPONSE_HEAD_CHARS]
        self._emit(result)

    def _emit(self, result: dict):
        self._last_result = result
        self.finished_with_result.emit(result)
