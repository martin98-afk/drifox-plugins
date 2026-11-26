"""对话控制器的状态与串行约束；不调用真实模型。"""

import time
from threading import Event

from ui.chat import Chat


class Result:
    def __init__(self, text="", error=None, cancelled=False, timed_out=False):
        self.text = text
        self.error = error
        self.cancelled = cancelled
        self.timed_out = timed_out

    @property
    def ok(self):
        return self.error is None and not self.cancelled and not self.timed_out


class FakeSession:
    def __init__(self, pieces, result=None, gate=None, late=""):
        self.pieces = list(pieces)
        self.result = result or Result(text="".join(pieces))
        self.gate = gate
        self.late = late
        self.calls = []
        self.cancelled = False
        self.cleaned = False

    def turn(self, messages, *, tools, timeout, callbacks):
        self.calls.append(messages)
        for piece in self.pieces:
            callbacks["content_received"](piece)
        if self.gate is not None:
            self.gate.wait(2)
        if self.late:
            callbacks["content_received"](self.late)
        return self.result

    def cancel(self):
        self.cancelled = True

    def cleanup(self):
        self.cleaned = True


def pump_until(qapp, predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_second_send_rejected_while_busy(qapp):
    sessions = []

    def create():
        session = FakeSession(["回答"], gate=Event())
        sessions.append(session)
        return session

    chat = Chat(create)
    assert chat.send("问一") is True
    assert chat.send("问二") is False
    assert len(sessions) == 1
    chat.stop()
    pump_until(qapp, lambda: chat.round is None)


def test_history_accumulates_across_rounds(qapp):
    sessions = []

    def create():
        session = FakeSession(["已回答"])
        sessions.append(session)
        return session

    chat = Chat(create)
    assert chat.send("问一")
    assert pump_until(qapp, lambda: chat.round is None)
    assert chat.send("问二")
    assert pump_until(qapp, lambda: chat.round is None)
    assert sessions[1].calls[0] == [
        {"role": "user", "content": "问一"},
        {"role": "assistant", "content": "已回答"},
        {"role": "user", "content": "问二"},
    ]
    assert sessions[0].cleaned and sessions[1].cleaned


def test_late_delta_after_stop_is_dropped(qapp):
    gate = Event()
    session = FakeSession(["首段"], gate=gate, late="迟到段")
    chat = Chat(lambda: session)
    received = []
    states = []
    chat.delta.connect(received.append)
    chat.state_changed.connect(states.append)
    assert chat.send("问")
    assert pump_until(qapp, lambda: received == ["首段"])
    chat.stop()
    gate.set()
    assert pump_until(qapp, lambda: chat.round is None)
    assert received == ["首段"]
    assert "迟到段" not in "".join(received)
    assert states[-1] == "stopped"
    assert chat.history == []


def test_failure_then_retry(qapp):
    attempts = []

    def create():
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("没有模型")
        return FakeSession(["成功"])

    chat = Chat(create)
    errors = []
    chat.terminal.connect(lambda state, text: errors.append((state, text)))
    assert chat.send("问") is False
    assert chat.round is None
    assert errors and errors[0][0] == "failed"
    assert chat.send("再问") is True
    assert pump_until(qapp, lambda: chat.round is None)
    assert chat.history[-1] == {"role": "assistant", "content": "成功"}


def test_shutdown_cancels_running_round(qapp):
    gate = Event()
    session = FakeSession([], gate=gate)
    chat = Chat(lambda: session)
    assert chat.send("问")
    chat.shutdown()
    assert session.cancelled
    gate.set()
