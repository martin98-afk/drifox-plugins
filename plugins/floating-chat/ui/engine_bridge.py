# -*- coding: utf-8 -*-
"""floating-chat 对话引擎桥。

职责：把主程序的 ``IsolatedChatContext``（独立 SessionManager + ToolExecutor +
ChatEngine）包装成「丢文本进去、流式吐出来」的控制器，并把 worker 线程的回调
桥接成 Qt 信号，保证 UI 只在主线程更新。

线程模型（关键，别改）：
- ``ChatEngine`` 在**主线程**构造（内部 UIConversationAdapter 是 QObject，
  归属线程决定信号投递上下文）；
- ``send()`` 内部 ``QEventLoop().exec()`` 阻塞等待 _PreSendWorker，
  必须放到 **QThread** 里跑，否则冻 UI；
- worker 回调在 worker 线程触发 → 只 emit 信号 → 主线程槽更新 UI。
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List, Optional

from loguru import logger
from PySide6.QtCore import QObject, QThread, Signal

PLUGIN_NAME = "floating-chat"

# 会话标题前缀（落主窗历史时用）
SESSION_TITLE_PREFIX = "快速对话"


class _StreamBridge(QObject):
    """worker 线程 → 主线程 的唯一通道（回调只 emit，不碰 QWidget）"""

    thinking = Signal()
    chunk = Signal(str)
    tool_started = Signal(str, str)  # tool_name, round
    tool_result = Signal(str, str)  # tool_name, result_text
    permission = Signal(str, str, dict)  # tool_call_id, tool_name, arguments
    finished = Signal()
    error = Signal(str)


class _SendThread(QThread):
    """跑一次 engine.send_message（阻塞调用隔离在后台线程）"""

    def __init__(self, engine, text: str, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._text = text

    def run(self):
        try:
            self._engine.send_message(self._text)
        except Exception as e:  # noqa: BLE001 — 后台线程异常必须落日志，不能静默吞
            logger.error(f"[{PLUGIN_NAME}] 发送失败: {e}")


class ChatController(QObject):
    """悬浮窗对话控制器（一个实例 = 一个独立会话）"""

    def __init__(self, host_widget, parent=None):
        super().__init__(parent)
        self._host = host_widget
        self._context = None
        self._engine = None
        self._session_id = ""
        self._model_signature = ""
        self._thread: Optional[_SendThread] = None
        self.bridge = _StreamBridge()

    # ── 查询 ──

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def is_streaming(self) -> bool:
        return bool(self._thread is not None and self._thread.isRunning())

    def model_label(self) -> str:
        cfg = self._current_model_config()
        name = str(cfg.get("模型名称", "") or "")
        provider = str(cfg.get("provider_name", "") or cfg.get("display_name", "") or "")
        if name and provider:
            return f"{provider} · {name}"
        return name or provider or "未配置模型"

    def round_count(self) -> int:
        session = self._current_session()
        if session is None:
            return 0
        return sum(1 for m in (session.messages or []) if isinstance(m, dict) and m.get("role") == "user")

    # ── 引擎生命周期 ──

    def _current_model_config(self) -> Dict[str, Any]:
        getter = getattr(self._host, "_get_current_model_config", None)
        if callable(getter):
            try:
                cfg = getter()
                return dict(cfg) if isinstance(cfg, dict) else {}
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[{PLUGIN_NAME}] 读取模型配置失败: {e}")
        return {}

    @staticmethod
    def _model_signature_of(cfg: Dict[str, Any]) -> str:
        """模型指纹：服务商+模型名变化即需重建引擎（配置其它字段变化无需重建）"""
        return f"{cfg.get('provider_name', '')}|{cfg.get('模型名称', '')}"

    def _build_engine(self, carry_messages: Optional[List[Dict]] = None) -> bool:
        """构建（或重建）隔离引擎；返回是否成功"""
        try:
            from app.core import ChatSession
            from app.gateway.local_service.isolated_context import IsolatedChatContext
        except Exception as e:  # noqa: BLE001
            logger.error(f"[{PLUGIN_NAME}] 隔离上下文导入失败: {e}")
            return False

        cfg = self._current_model_config()
        if not cfg:
            logger.warning(f"[{PLUGIN_NAME}] 宿主无可用模型配置")
            return False

        target = None
        if carry_messages:
            target = ChatSession(name=f"{SESSION_TITLE_PREFIX}")
            target.set_messages(list(carry_messages))

        try:
            self._context = IsolatedChatContext(
                context_id=str(uuid.uuid4()),
                main_widget=self._host,
                target_session=target,
                model_config=cfg,
            )
            self._engine = self._context.create_chat_engine(
                worker_callbacks=self._make_callbacks(),
                api_mode=True,
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f"[{PLUGIN_NAME}] 引擎构建失败: {e}")
            self._context = None
            self._engine = None
            return False

        session = self._current_session()
        self._session_id = session.session_id if session else ""
        self._model_signature = self._model_signature_of(cfg)
        return True

    def _make_callbacks(self) -> Dict[str, Callable]:
        b = self.bridge
        return {
            "thinking_started": lambda: b.thinking.emit(),
            "content_received": lambda p: b.chunk.emit(str(p or "")),
            "tool_call_started": lambda _i, name, _a, r="": b.tool_started.emit(str(name), str(r)),
            "tool_result_received": lambda _i, name, _a, r=None: b.tool_result.emit(
                str(name), str(r)[:200]
            ),
            "permission_approval_requested": lambda i, n, a: b.permission.emit(
                str(i), str(n), dict(a or {})
            ),
            "stream_finished": lambda _r=None: b.finished.emit(),
            "error": lambda e: b.error.emit(str(e)),
        }

    def _current_session(self):
        if self._context is None:
            return None
        return self._context.get_current_session()

    def ensure_engine(self) -> bool:
        """确保引擎可用；模型配置变化时重建并搬运历史消息"""
        cfg = self._current_model_config()
        if self._engine is not None:
            if self._model_signature_of(cfg) == self._model_signature:
                return True
            # 模型换了：搬走历史消息，用新配置重建（模型能力/参数随配置走）
            session = self._current_session()
            carried = list((session.messages if session is not None else None) or [])
            self.reset_session()
            return self._build_engine(carry_messages=carried)
        return self._build_engine()

    def reset_session(self):
        """丢弃当前会话（「新会话」入口）"""
        if self._context is not None:
            try:
                self._context.cleanup()
            except Exception as e:  # noqa: BLE001
                logger.debug(f"[{PLUGIN_NAME}] 上下文清理失败: {e}")
        self._context = None
        self._engine = None
        self._session_id = ""

    # ── 发送 / 停止 ──

    def send(self, text: str) -> bool:
        if not text.strip():
            return False
        if self.is_streaming:
            return False
        if not self.ensure_engine():
            self.bridge.error.emit("没有可用的模型配置，请先在主窗配置服务商与模型")
            return False

        self._thread = _SendThread(self._engine, text, self)
        self._thread.start()
        return True

    def stop(self):
        """取消当前流（非阻塞）。cancel 后 engine 的 stream_finished 会被
        is_streaming 守卫吞掉，故结束动作由 UI 侧自行收敛（幂等）。"""
        if self._engine is not None:
            try:
                self._engine._conversation_executor.cancel_worker()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[{PLUGIN_NAME}] 停止失败: {e}")
        if self._thread is not None:
            self._thread.quit()
            self._thread = None

    def decide_permission(self, tool_call_id: str, allow: bool, remember: str = ""):
        if self._engine is None:
            return
        try:
            self._engine.decide_tool_permission(
                tool_call_id, "allow" if allow else "deny", remember=remember
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[{PLUGIN_NAME}] 权限决策失败: {e}")

    # ── 持久化：写主窗历史 ──

    def persist_to_history(self) -> Optional[str]:
        """把当前会话写进宿主窗口的历史，返回 session_id（失败返回 None）

        ⚠️ 不走 APIHistoryManager：它写独立 SQLite 且只留 100 条，
        主窗历史面板翻不到。这里直接写宿主的 history_manager。
        """
        session = self._current_session()
        hm = getattr(self._host, "history_manager", None)
        if session is None or hm is None:
            return None
        messages = list(session.messages or [])
        if not messages:
            return None
        title = self._make_title(messages)
        try:
            hm.save_session(messages=messages, title=title, session_id=session.session_id)
            return session.session_id
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[{PLUGIN_NAME}] 会话落历史失败: {e}")
            return None

    def _make_title(self, messages: List[Dict]) -> str:
        for m in messages:
            if isinstance(m, dict) and m.get("role") == "user":
                content = m.get("content", "")
                if isinstance(content, list):
                    text = " ".join(
                        str(p.get("text", "")) for p in content if isinstance(p, dict)
                    )
                else:
                    text = str(content)
                text = " ".join(text.split())
                if text:
                    return f"{SESSION_TITLE_PREFIX} · {text[:20]}"
        return SESSION_TITLE_PREFIX

    def dispose(self):
        """窗口销毁时释放资源"""
        self.stop()
        self.reset_session()
