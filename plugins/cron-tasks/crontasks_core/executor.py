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
        self._timeout_seconds: int = 0  # 0 = 默认（EXECUTION_TIMEOUT_SECONDS）
        self._session: Any = None
        self._cancelled = False
        self._cancel_dispatched = False  # session.cancel 是否已异步下发（防重复起线程）
        self._started_at: float = 0.0  # run() 起始时刻（stop 兜底记录算时长用）
        self._last_result: Optional[dict] = None  # run() 结束时保存（停止收尾用）

    def configure(
        self,
        job: CronJob,
        services: Dict[str, Any],
        system_prompt: str = "",
        tools: Optional[List[Dict]] = None,
        model_config_override: Optional[Dict[str, Any]] = None,
        timeout_seconds: int = 0,
    ):
        self._job = job
        self._services = services
        self._system_prompt = system_prompt
        self._tools = tools
        self._model_override = model_config_override
        self._timeout_seconds = timeout_seconds or 0

    def cancel(self):
        """非阻塞取消：置标志 + 异步唤醒 session.cancel()

        session.cancel() 链路（EngineSession → ConversationExecutor.cancel_worker）
        内部持锁并逐个断开 worker 信号，实测存在长时间阻塞的可能：同步调用会
        连累调用方——scheduler.stop 卡主线程、看门狗卡在强制收尾之前（2026-09-11
        实测：超时点后无任何收尾日志与落盘，任务永久悬挂）。故改旁路 daemon
        线程下发，cancel() 本身立即返回。
        """
        self._cancelled = True
        session = self._session
        if session is None or self._cancel_dispatched:
            return
        self._cancel_dispatched = True
        try:
            threading.Thread(
                target=self._send_session_cancel,
                args=(session,),
                daemon=True,
                name="cron-session-cancel",
            ).start()
        except Exception:
            pass

    @staticmethod
    def _send_session_cancel(session):
        """旁路线程：真正的 session.cancel()，异常丢弃不冒泡"""
        try:
            session.cancel()
        except Exception:
            pass

    # ---------------------------------------------------------------

    def run(self):  # noqa: C901
        job = self._job
        started = time.monotonic()
        self._started_at = started
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
                # hook_policy_id="cron_selective"：hook 节点白名单可配置
                # （<app_data>/plugin_data/cron-tasks/hook_policy.json，
                # 默认 SessionStart+PreToolUse+PostToolUse）。策略实现见本插件
                # hook_policies/cron_selective.py；SessionStart 触发需主程序
                # EngineSession 支持（app/core/conversation/engine_session.py）。
                session = (
                    create_session(
                        "cron-tasks",
                        model_config_override=self._model_override,
                        hook_policy_id="cron_selective",
                    )
                    if self._model_override
                    else create_session("cron-tasks", hook_policy_id="cron_selective")
                )
                if self._cancelled:
                    holder["cancelled"] = True
                    return
                self._session = session
                result = session.turn(
                    system=(self._system_prompt or None),
                    user=job.prompt,
                    tools=self._tools or [],
                    timeout=self._timeout_seconds or EXECUTION_TIMEOUT_SECONDS,
                )
                if getattr(result, "cancelled", False) or self._cancelled:
                    holder["cancelled"] = True
                elif getattr(result, "timed_out", False):
                    _secs = self._timeout_seconds or EXECUTION_TIMEOUT_SECONDS
                    holder["timeout"] = f"执行超时（>{_secs // 60} 分钟）"
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

        # 硬看门狗：不信任 turn() 内部超时。实测（2026-09-11）daemon 线程场景下
        # 流式读取挂死后，turn 内部 adapter.wait(timeout) 的超时收尾整链未发生
        # （两个 20min 超时点均无落盘/通知），任务状态/串行锁/gateway 通知全部卡死。
        # 故由 QThread 主体自查运行时长：超时+缓冲仍无结果 → 强制取消并收尾。
        hard_timeout = self._timeout_seconds or EXECUTION_TIMEOUT_SECONDS
        hard_deadline = started + hard_timeout + 60.0  # 缓冲 60s 让 turn 内部超时先行
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
            if time.monotonic() > hard_deadline:
                self.cancel()  # 尽力下发取消
                if done.wait(CANCEL_GRACE_SECONDS):
                    break  # turn 恰在此间返回，走正常收尾（holder 应为 timeout/error）
                duration_ms = int((time.monotonic() - started) * 1000)
                logger.warning(
                    f"[cron-tasks] turn 超时 {hard_timeout}s+60s 缓冲仍未返回，执行器强制收尾"
                )
                self._emit(
                    {
                        "job_id": job.id,
                        "status": "timeout",
                        "error": f"执行超时（>{hard_timeout // 60} 分钟，强制收尾）",
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
