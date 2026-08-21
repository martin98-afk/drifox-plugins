# -*- coding: utf-8 -*-
"""taskboard 任务工作线程 — 单任务单列一次完整对话处理

每个 TaskWorker 绑定 (task, column)：以该列绑定智能体的 system prompt +
任务包驱动一次完整对话（含多轮工具调用），解析响应末尾的去留信号。

并行模型：每个任务独立 QThread + 独立 ConversationCore 执行栈
（经 services["conversation_stack"]() 工厂创建），互不共享执行器。
"""

import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger
from PyQt5.QtCore import QCoreApplication, QEventLoop, QThread, QTimer, pyqtSignal

from taskboard_core.adapter import TaskConversationAdapter
from taskboard_core.config import (
    COLUMN_META,
    COLUMNS,
    SIGNAL_ADVANCE,
    SIGNAL_DROP,
    SIGNAL_HOLD,
    SUMMARY_MAX_CHARS,
    TASK_TIMEOUT_SECONDS,
    VALID_SIGNALS,
)
from taskboard_core.models import Task

# 信号解析：响应中最后一次出现的合法信号（独立成行）
_SIGNAL_RE = re.compile(
    r"^\s*(TASK_ADVANCE|TASK_HOLD|TASK_DROP)\s*$", re.MULTILINE
)


def parse_signal(response: str) -> Optional[str]:
    """解析响应末尾的去留信号；未找到返回 None（默认 HOLD）"""
    matches = _SIGNAL_RE.findall(response or "")
    if not matches:
        return None
    sig = matches[-1]
    return sig if sig in VALID_SIGNALS else None


def strip_signal(response: str) -> str:
    """去掉信号行后的响应正文"""
    return _SIGNAL_RE.sub("", response or "").strip()


def build_summary(response: str) -> str:
    """从响应正文提取单行摘要（任务卡片显示用）"""
    body = strip_signal(response)
    # 取第一个非空段落，压平换行
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    if not lines:
        return ""
    summary = " ".join(lines)
    if len(summary) > SUMMARY_MAX_CHARS:
        summary = summary[:SUMMARY_MAX_CHARS] + "…"
    return summary


class TaskWorker(QThread):
    """单任务处理器 — 一个 (task, column) 一次完整对话"""

    # (task_id, log_text)：离散事件日志（时间戳行）
    task_log = pyqtSignal(str, str)
    # (task_id, preview)：流式内容预览（实时覆盖）
    task_update = pyqtSignal(str, str)
    # (task_id, signal, summary, report)：处理完成（signal ∈ VALID_SIGNALS|""）
    task_finished = pyqtSignal(str, str, str, str)
    # (task_id, error)
    task_error = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._task: Optional[Task] = None
        self._column: str = ""
        self._agent_name: str = ""
        self._log_file: Optional[Path] = None

        self._model_config_getter: Optional[Callable[[], Dict]] = None
        self._tool_executor: Optional[Any] = None
        self._tools_schema: List[Dict] = []
        self._agent_prompt_getter: Optional[Callable[[str], str]] = None
        self._agent_manager: Optional[Any] = None
        self._conversation_stack: Optional[Any] = None

        self._conversation_executor: Optional[Any] = None
        self._adapter: Optional[TaskConversationAdapter] = None
        self._is_cancelled = False
        self._task_error_buf: str = ""  # 最近一次错误文本（诊断与收尾显示用）

    # ================================================================
    #  配置（start 前调用）
    # ================================================================

    def configure(
        self,
        task: Task,
        column: str,
        services: Dict[str, Any],
        log_file: Optional[Path] = None,
    ):
        """配置 worker

        Args:
            task: 任务对象（快照语义：worker 只读标题/描述/上下文链，
                  状态流转由 controller 在 task_finished 后统一执行）
            column: 处理时的列（决定智能体与职责提示）
            services: UI context services（main_widget._build_ui_services）
            log_file: 处理日志落盘文件（可空）
        """
        self._task = task
        self._column = column if column in COLUMNS else task.status
        self._agent_name = COLUMN_META.get(self._column, {}).get("agent", "")
        self._log_file = log_file

        self._model_config_getter = services.get("get_model_config")
        self._tool_executor = services.get("get_tool_executor", lambda: None)()
        self._tools_schema = services.get("get_tools_schema", lambda _n: [])(self._agent_name)
        self._agent_prompt_getter = services.get("get_agent_prompt")
        self._agent_manager = services.get("get_agent_manager", lambda: None)()
        self._conversation_stack = services.get("conversation_stack", lambda: None)()

        stack = self._conversation_stack
        if stack is None:
            from app.core.conversation.core import ConversationCore

            class _FallbackStack:
                @staticmethod
                def create_core(get_model_config, agent_manager=None, backend=None, session_manager=None):
                    return ConversationCore.create(
                        get_model_config=get_model_config,
                        agent_manager=agent_manager,
                        backend=backend,
                        session_manager=session_manager,
                    )

                @staticmethod
                def create_executor(core, config=None, tool_executor=None, agent_manager=None):
                    from app.core.conversation.executor import ConversationExecutor

                    return ConversationExecutor(
                        core=core, config=config, tool_executor=tool_executor, agent_manager=agent_manager
                    )

            stack = _FallbackStack()

        from app.core.conversation.config import ConversationConfig, PermissionStrategy

        conv_config = ConversationConfig(permission_strategy=PermissionStrategy.AUTO_ALLOW)
        core = stack.create_core(
            get_model_config=self._model_config_getter,
            agent_manager=self._agent_manager,
            backend=None,
        )
        self._conversation_executor = stack.create_executor(
            core=core,
            config=conv_config,
            tool_executor=self._tool_executor,
            agent_manager=self._agent_manager,
        )
        self._adapter = TaskConversationAdapter(core=core, executor=self._conversation_executor)

    @property
    def task_id(self) -> str:
        return self._task.id if self._task else ""

    def _diag(self, text: str, emit: bool = False):
        """诊断日志：loguru 记录 + 追加落盘；emit=True 时同时广播到卡片日志

        保证：任何一次 start_task 成功后，logs/<task_id>.md 必然产生文件。
        """
        logger.info(f"[taskboard] task={self.task_id} {text}")
        if emit:
            self._emit_log(text)
        if self._log_file:
            try:
                from datetime import datetime

                self._log_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self._log_file, "a", encoding="utf-8") as f:
                    f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")
            except Exception as e:
                logger.debug(f"[taskboard] 诊断日志落盘失败: {e}")

    def cancel(self):
        """取消处理（非阻塞）：置标志 + 取消当前对话"""
        self._is_cancelled = True
        if self._conversation_executor:
            try:
                self._conversation_executor.cancel_worker()
            except Exception:
                pass

    # ================================================================
    #  主流程
    # ================================================================

    def run(self):
        if not self._task or not self._conversation_executor:
            logger.warning(f"[taskboard] worker 未配置即启动 task={getattr(self._task, 'id', None)}")
            return
        tid = self._task.id
        try:
            model_name = ""
            try:
                if self._model_config_getter:
                    mc = self._model_config_getter() or {}
                    model_name = f"{mc.get('服务商名', '')}/{mc.get('模型名称', '')}"
            except Exception:
                pass
            self._diag(
                f"START column={self._column} agent=@{self._agent_name} model={model_name or '?'}",
                emit=True,
            )

            response = self._execute_conversation()
            self._diag(f"conversation done, cancelled={self._is_cancelled}, "
                       f"response_len={len(response) if response else 0}")

            if self._is_cancelled:
                self._diag("CANCELLED by user", emit=True)
                self.task_finished.emit(tid, "", "已手动停止", "")
                return
            if response is None:
                err = self._task_error_buf or "对话未返回结果"
                self._diag(f"FAILED: {err}", emit=True)
                self.task_finished.emit(tid, SIGNAL_HOLD, f"处理失败：{err}", "")
                return

            signal = parse_signal(response)
            summary = build_summary(response)
            report = response.strip() if self._column == "done" else ""
            if self._column == "done":
                signal = SIGNAL_HOLD
                summary = summary or "已完成总结归档"
            elif not summary:
                # 假完成修复：空响应绝不能静默"处理完成"
                summary = "⚠ 模型返回空响应（未产出结论），请检查模型配置或重试"
                self._diag("EMPTY RESPONSE — no usable content", emit=True)
            self._diag(f"RESULT signal={signal} summary_len={len(summary)}")
            self._append_log(response)
            self.task_finished.emit(tid, signal or SIGNAL_HOLD, summary, report)
        except Exception as e:
            logger.exception(f"[taskboard] worker 异常 task={tid}")
            self._diag(f"EXCEPTION: {e}", emit=True)
            self.task_error.emit(tid, str(e))
            self.task_finished.emit(tid, SIGNAL_HOLD, f"处理异常：{e}", "")
        finally:
            self._append_log(None)

    # ================================================================
    #  对话执行（参考 autoloop 的同步等待模式）
    # ================================================================

    def _execute_conversation(self) -> Optional[str]:
        """执行一次完整对话，返回响应文本；失败/取消返回 None"""
        tid = self._task.id
        self._adapter.reset()

        # 残留流式状态复位（上轮竞态防御，与 autoloop 同源问题）
        if self._conversation_executor.is_streaming:
            _stale = self._conversation_executor.get_current_worker()
            if not self._alive_worker(_stale):
                self._conversation_executor._is_streaming = False
                self._conversation_executor._current_worker = None
                self._emit_log("🔓 复位残留的流式状态")

        llm_config = self._model_config_getter() if self._model_config_getter else {}
        messages = self._build_messages()

        success = self._conversation_executor.execute(
            messages=messages,
            llm_config=llm_config,
            tools=self._tools_schema,
            callbacks=self._make_callbacks(),
        )
        if not success:
            self._diag("executor.execute returned False（可能已有对话在流式中）", emit=True)
            self._task_error_buf = "Worker 启动失败（可能已有对话流式中）"
            self.task_error.emit(tid, self._task_error_buf)
            return None

        response = self._wait_worker_finish()
        if self._is_cancelled:
            return None
        if response is None:
            err = (self._adapter.get_error() or "") if self._adapter else ""
            self._task_error_buf = err or "对话未返回结果"
            self.task_error.emit(tid, self._task_error_buf)
            return None
        resp = response
        if not resp.strip():
            self._task_error_buf = "模型返回空内容"
        return resp

    def _wait_worker_finish(self) -> Optional[str]:
        """等待 ChatWorker 完成（QEventLoop + 兜底轮询），返回响应文本"""
        worker = self._conversation_executor.get_current_worker()
        if not worker:
            worker = getattr(self._conversation_executor, "_finalize_worker", None)

        if self._alive_worker(worker):
            loop = QEventLoop()
            worker.finished.connect(loop.quit)
            timeout_timer = QTimer()
            timeout_timer.setSingleShot(True)
            timeout_timer.timeout.connect(loop.quit)
            timeout_timer.start(60000)
            loop.exec_()
            timeout_timer.stop()

            elapsed = 0
            while self._alive_worker(worker) and worker.isRunning() and not self._is_cancelled:
                if elapsed >= TASK_TIMEOUT_SECONDS:
                    self._emit_log(f"⚠️ 任务超时（{TASK_TIMEOUT_SECONDS}s），中断处理")
                    worker.cancel()
                    worker.requestInterruption()
                    break
                worker.wait(1000)
                elapsed += 1
                QCoreApplication.processEvents()

            if self._is_cancelled and self._alive_worker(worker) and worker.isRunning():
                worker.cancel()
                worker.requestInterruption()
                worker.wait(3000)
            if self._alive_worker(worker):
                self._conversation_executor._on_worker_finished(worker)
            QCoreApplication.processEvents()
        else:
            if not self._adapter.wait_for_completion(timeout=TASK_TIMEOUT_SECONDS):
                return None

        if self._adapter.get_error():
            return None
        return self._adapter.get_response() or ""

    # ================================================================
    #  消息构建
    # ================================================================

    def _build_messages(self) -> List[Dict]:
        task = self._task
        system_prompt = ""
        if self._agent_prompt_getter:
            system_prompt = self._agent_prompt_getter(self._agent_name) or ""

        lines = [
            "# 任务看板任务处理",
            "",
            f"## 当前列：{COLUMN_META.get(self._column, {}).get('title', self._column)}"
            f"（由 @{self._agent_name} 处理）",
            "",
            f"## 任务标题",
            task.title,
            "",
            "## 任务描述",
            task.detail or "（用户未提供详细描述，按标题理解任务）",
        ]

        if task.context_log:
            lines += ["", "## 前序处理记录（各列智能体的结论链）"]
            for rec in task.context_log:
                col = COLUMN_META.get(rec.get("column", ""), {}).get("title", rec.get("column", ""))
                lines.append(f"- [{col} / @{rec.get('agent', '')}] {rec.get('summary', '')}")

        if task.error:
            lines += ["", f"## 上次错误（供参考）", task.error]

        lines += [
            "",
            "## 输出要求",
            "完成本列职责后，在响应**末尾单独一行**输出你的去留决定（三选一）：",
            f"- `{SIGNAL_ADVANCE}` — 本列职责已完成，推进到下一列",
            f"- `{SIGNAL_HOLD}` — 保留在当前列，等待用户再次触发处理",
            f"- `{SIGNAL_DROP}` — 该任务无价值或无法完成，删除它",
            "正文部分给出简明处理结论（将显示在任务卡片上）。",
        ]
        if self._column == "done":
            lines[-1] = "正文部分输出完整的任务总结报告（Markdown 格式，含成果、改动、验证结论）。"

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(lines)},
        ]

    # ================================================================
    #  回调包装（流式预览 + 日志落盘）
    # ================================================================

    def _make_callbacks(self) -> Dict[str, Callable]:
        import time

        callbacks = dict(self._adapter.get_callbacks())
        _buf = [""]
        _last_emit = [0.0]
        _THROTTLE = 0.3

        def _on_content(piece: str):
            _buf[0] += piece or ""
            now = time.time()
            if now - _last_emit[0] > _THROTTLE:
                _last_emit[0] = now
                preview = _buf[0].replace("\n", " ")[-80:]
                self.task_update.emit(self.task_id, preview)

        callbacks["content_received"] = _on_content

        _orig_finished = callbacks.get("finished")
        _orig_error = callbacks.get("error")

        def _on_finished(response: str):
            self._append_log(response)
            if _orig_finished:
                _orig_finished(response)

        def _on_error(error: str):
            self._append_log(f"[ERROR] {error}")
            if _orig_error:
                _orig_error(error)

        callbacks["finished"] = _on_finished
        callbacks["error"] = _on_error
        return callbacks

    # ================================================================
    #  工具
    # ================================================================

    def _emit_log(self, text: str):
        from datetime import datetime

        stamp = datetime.now().strftime("%H:%M:%S")
        self.task_log.emit(self.task_id, f"[{stamp}] {text}")

    def _append_log(self, response: Optional[str]):
        """处理日志追加落盘（.taskboard/logs/<task_id>.md）"""
        if not self._log_file:
            return
        try:
            from datetime import datetime

            self._log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(
                    f"\n\n---\n## {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    f" · 列={self._column} · 智能体=@{self._agent_name}\n\n"
                )
                if response:
                    f.write(response)
        except Exception as e:
            logger.debug(f"[taskboard] 日志落盘失败: {e}")

    @staticmethod
    def _alive_worker(w) -> bool:
        if w is None:
            return False
        try:
            w.isRunning()
            return True
        except RuntimeError:
            return False
