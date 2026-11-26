"""面板交互：收起不打断、Esc、输入法回车和停止按钮。"""

import time

from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QKeyEvent

from ui.panel import Panel, markdown_html

from test_chat import FakeSession


def key(kind, code, modifiers=Qt.NoModifier):
    return QKeyEvent(kind, code, modifiers)


def create_session():
    return FakeSession(["回答"], gate=__import__("threading").Event())


def test_collapse_keeps_round_running(qapp):
    panel = Panel(create_session)
    panel.expand()
    qapp.processEvents()
    panel.input.setPlainText("问题")
    panel.submit()
    assert panel.chat.round is not None
    panel.collapse()
    assert panel.chat.round is not None
    assert panel.capsule.isVisible()
    assert not panel.card.isVisible()
    assert "等待回复" in panel.capsule.text()
    panel.chat.shutdown()
    panel.close()


def test_escape_collapses_without_sending(qapp):
    panel = Panel(create_session)
    panel.expand()
    qapp.processEvents()
    panel.input.setPlainText("草稿")
    panel.input.keyPressEvent(key(QEvent.KeyPress, Qt.Key_Escape))
    assert not panel.expanded
    assert panel.input.toPlainText() == "草稿"
    assert panel.chat.round is None
    panel.close()


def test_ime_enter_does_not_send(qapp):
    panel = Panel(create_session)
    panel.expand()
    panel.input.setPlainText("拼音")
    panel.input.composing = True
    panel.input.keyPressEvent(key(QEvent.KeyPress, Qt.Key_Return))
    assert panel.chat.round is None
    panel.input.composing = False
    panel.input.keyPressEvent(key(QEvent.KeyPress, Qt.Key_Return))
    assert panel.chat.round is not None
    panel.chat.shutdown()
    panel.close()


def test_send_becomes_stop_while_busy(qapp):
    panel = Panel(create_session)
    panel.expand()
    panel.input.setPlainText("问题")
    panel.submit()
    assert panel.send.text().startswith("停止")
    panel.send.click()
    assert panel.chat.round is not None
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and panel.chat.round is not None:
        qapp.processEvents()
        time.sleep(0.01)
    assert panel.chat.round is None
    assert panel.state == "stopped"
    panel.close()


def test_markdown_renders_without_escaping_html(qapp):
    html = markdown_html("### 标题\n- **粗体**与 `code`\n\n<script>x</script>")
    assert "<b>标题</b>" in html
    assert "• <b>粗体</b>与 <code>code</code>" in html
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_empty_input_does_not_send(qapp):
    panel = Panel(create_session)
    panel.expand()
    panel.submit()
    assert panel.chat.round is None
    panel.close()
