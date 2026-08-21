# -*- coding: utf-8 -*-
"""taskboard 对话适配器 — 线程同步（类型仅注解用，避免模块级 deep import）

与 autoloop 的 AutoLoopConversationAdapter 同构：TaskWorker 工作在 QThread，
通过 threading.Event 等待对话完成，不走 Qt 信号中转。
"""

import threading
from typing import TYPE_CHECKING, Callable, Dict, Optional

if TYPE_CHECKING:
    from app.core.conversation.adapters.base import BaseConversationAdapter  # noqa: F401
    from app.core.conversation.core import ConversationCore  # noqa: F401
    from app.core.conversation.executor import ConversationExecutor  # noqa: F401


class TaskConversationAdapter("BaseConversationAdapter" if TYPE_CHECKING else object):
    """任务对话适配器 — 线程同步等待"""

    def __init__(self, core: "ConversationCore", executor: "ConversationExecutor"):
        self._core = core  # type: ignore[assignment]
        self._executor = executor  # type: ignore[assignment]
        self._worker_done_event = threading.Event()
        self._response: str = ""
        self._error: Optional[str] = None

    # taskboard 自建消息，不委托 ContextBudgetAllocator
    def build_messages(self, session, llm_config, current_agent=None):
        raise NotImplementedError("taskboard 自建消息，不经过此路径")

    def on_content_received(self, piece: str):
        pass  # 流式内容经 executor callbacks 包装层转发，不在此处理

    def on_finished(self, response: str):
        self._response = response
        self._worker_done_event.set()

    def on_error(self, error: str):
        self._error = error
        self._worker_done_event.set()

    def wait_for_completion(self, timeout: float = 30.0) -> bool:
        return self._worker_done_event.wait(timeout=timeout)

    def get_response(self) -> str:
        return self._response

    def get_error(self) -> Optional[str]:
        return self._error

    def reset(self):
        self._response = ""
        self._error = None
        self._worker_done_event.clear()

    def get_callbacks(self) -> Dict[str, Callable]:
        return {
            "content_received": self.on_content_received,
            "finished": self.on_finished,
            "error": self.on_error,
        }
