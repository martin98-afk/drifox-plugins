"""隔离对话：公开宿主契约、真实增量与串行状态。"""

import uuid
from datetime import datetime
from queue import Empty, SimpleQueue
from threading import Event, Lock, Thread
from time import monotonic

from PyQt5.QtCore import QObject, QTimer, pyqtSignal


class Round:
    def __init__(self, session, messages, tools=None):
        self.session = session
        self.messages = messages
        self.tools = list(tools or [])
        self.events = SimpleQueue()
        self.stopping = Event()
        self.finished = Event()
        self.lock = Lock()
        self.deadline = monotonic() + 330
        self.thread = Thread(target=self.run, name="notch-chat-turn", daemon=True)

    def run(self):
        state, answer = "failed", "模型请求失败。请检查当前模型配置后重试。"
        try:
            result = self.session.turn(
                messages=self.messages, tools=self.tools, timeout=300,
                callbacks={"content_received": self.on_delta},
            )
            if result.cancelled:
                state, answer = "stopped", ""
            elif result.timed_out:
                answer = "模型回复超时，可以重试。"
            elif result.ok and result.text.strip():
                state, answer = "done", result.text
        except Exception:
            pass
        finally:
            with self.lock:
                try:
                    self.session.cleanup()
                except Exception:
                    pass
                self.finished.set()
                self.events.put((state, answer))

    def on_delta(self, piece):
        if isinstance(piece, str) and piece and not self.stopping.is_set() and not self.finished.is_set():
            self.events.put(("chunk", piece))

    def cancel(self):
        if self.stopping.is_set() or self.finished.is_set():
            return
        self.stopping.set()

        def cancel_worker():
            with self.lock:
                if not self.finished.is_set():
                    try:
                        self.session.cancel()
                    except Exception:
                        pass

        Thread(target=cancel_worker, name="notch-chat-cancel", daemon=True).start()


class Chat(QObject):
    state_changed = pyqtSignal(str)
    delta = pyqtSignal(str)
    terminal = pyqtSignal(str, str)

    def __init__(self, create, parent=None):
        super().__init__(parent)
        self.create = create
        self.history = []
        self.round = None
        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self.drain)

    def send(self, text, tools=None):
        text = text.strip()
        if self.round is not None or not text:
            return False
        try:
            session = self.create()
        except Exception:
            self.state_changed.emit("failed")
            self.terminal.emit("failed", "无法启动对话。请在主窗口选择可用模型后重试。")
            return False
        messages = [*self.history, {"role": "user", "content": text}]
        self.round = Round(session, messages, tools)
        self.state_changed.emit("waiting")
        self.timer.start()
        self.round.thread.start()
        return True

    def stop(self):
        if self.round is not None:
            self.round.cancel()
            self.state_changed.emit("stopping")

    def drain(self):
        turn = self.round
        if turn is None:
            return
        while True:
            try:
                state, text = turn.events.get_nowait()
            except Empty:
                if monotonic() >= turn.deadline:
                    turn.cancel()
                    self.finish("failed", "模型未及时结束，请重试。")
                return
            if state == "chunk":
                if not turn.stopping.is_set():
                    self.state_changed.emit("streaming")
                    self.delta.emit(text)
                continue
            if turn.stopping.is_set():
                state, text = "stopped", ""
            elif state == "done":
                self.history = [*turn.messages, {"role": "assistant", "content": text}]
            self.finish(state, text)
            return

    def finish(self, state, text):
        self.timer.stop()
        self.round = None
        self.state_changed.emit(state)
        self.terminal.emit(state, text)

    def snapshot(self, title):
        """把本窗对话整理成宿主可落库的会话快照。"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        messages = [dict(m) for m in self.history]
        return {
            "session_id": str(uuid.uuid4()),
            "name": title,
            "messages": messages,
            "topic_summary": "",
            "created_at": now,
            "last_updated": now,
            "message_count": len(messages),
            "system_prompt": "",
            "metadata": {},
            "user_edited_title": True,
            "originating_project": "",
            "is_temp": False,
        }

    def shutdown(self):
        self.timer.stop()
        if self.round is not None:
            self.round.cancel()
            self.round = None
