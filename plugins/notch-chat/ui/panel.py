"""同一枚顶边胶囊的收起态与展开态。"""

import re
import sys
from html import escape

from loguru import logger

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QTextCursor
from PyQt5.QtWidgets import (
    QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QSizePolicy, QTextBrowser, QVBoxLayout, QWidget,
)

from .chat import Chat

def markdown_html(text):
    """把常见的 markdown 记号转成 QTextBrowser 认得的 HTML。"""
    out = escape(text)
    out = re.sub(r"```[^\n]*\n(.*?)```", lambda m: f"<pre>{m.group(1)}</pre>", out, flags=re.S)
    out = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*\n]+)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?m)^#{1,6}\s*(.+)$", r"<b>\1</b>", out)
    out = re.sub(r"(?m)^\s*[-*]\s+", "• ", out)
    return out


STATUS = {
    "idle": "待机", "waiting": "等待回复", "streaming": "正在回复",
    "done": "已完成", "stopping": "正在停止", "stopped": "已停止", "failed": "发送失败",
}
BUSY = {"waiting", "streaming", "stopping"}
MARK = {
    "idle": "○", "waiting": "◐", "streaming": "●", "done": "✓",
    "stopping": "◌", "stopped": "■", "failed": "!",
}


class Composer(QPlainTextEdit):
    submit = pyqtSignal()
    collapse = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.composing = False

    def inputMethodEvent(self, event):
        self.composing = bool(event.preeditString())
        super().inputMethodEvent(event)

    def keyPressEvent(self, event):
        if not self.composing and event.key() == Qt.Key_Escape:
            self.collapse.emit()
        elif not self.composing and event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (
            event.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)
        ):
            self.submit.emit()
        else:
            super().keyPressEvent(event)


class Panel(QWidget):
    def __init__(self, create, parent=None, *, dark=False):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("顶边快捷对话")
        self.expanded = False
        self.state = "idle"
        self.transcript = []
        self.partial = ""
        self.current_prompt = ""
        self.hotkey_hint = "Esc 收起"
        self._pinned = False
        self._tool_schema = None
        self.chat = Chat(create, self)
        self.chat.state_changed.connect(self.set_state)
        self.chat.delta.connect(self.append_delta)
        self.chat.terminal.connect(self.finish)
        self.capsule = QPushButton(self)
        self.capsule.setObjectName("capsule")
        self.capsule.setCursor(Qt.PointingHandCursor)
        self.capsule.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.capsule.clicked.connect(self.expand)
        self.card = QFrame(self, objectName="chatCard")
        self.card.setAttribute(Qt.WA_StyledBackground, True)
        for widget in (self.capsule, self.card):
            shadow = QGraphicsDropShadowEffect(widget)
            shadow.setBlurRadius(20)
            shadow.setOffset(0, 4)
            shadow.setColor(QColor(0, 0, 0, 52))
            widget.setGraphicsEffect(shadow)
        box = QVBoxLayout(self.card)
        box.setContentsMargins(18, 12, 18, 10)
        box.setSpacing(9)
        header = QHBoxLayout()
        title = QLabel("快捷对话", objectName="title")
        header.addWidget(title)
        self.badge = QLabel(objectName="badge")
        header.addWidget(self.badge)
        header.addStretch()
        collapse = QPushButton("收起  ⌃", objectName="quiet")
        collapse.clicked.connect(self.collapse)
        header.addWidget(collapse)
        box.addLayout(header)
        self.reply = QTextBrowser(objectName="reply")
        self.reply.viewport().setAutoFillBackground(False)
        self.reply.setOpenLinks(False)
        box.addWidget(self.reply, 1)
        compose = QFrame(objectName="compose")
        compose.setAttribute(Qt.WA_StyledBackground, True)
        row = QHBoxLayout(compose)
        row.setContentsMargins(8, 5, 7, 5)
        self.input = Composer()
        self.input.viewport().setAutoFillBackground(False)
        self.input.setPlaceholderText("问点什么…")
        self.input.setFixedHeight(48)
        self.input.submit.connect(self.submit)
        self.input.collapse.connect(self.collapse)
        row.addWidget(self.input, 1)
        self.send = QPushButton("发送  ↑", objectName="send")
        self.send.setMinimumWidth(68)
        self.send.clicked.connect(self.submit)
        row.addWidget(self.send)
        box.addWidget(compose)
        footer = QHBoxLayout()
        footer.setContentsMargins(2, 0, 0, 0)
        self.hints = QLabel(objectName="hints")
        footer.addWidget(self.hints)
        footer.addStretch()
        self.new_button = QPushButton("新会话", objectName="quiet")
        self.new_button.setCursor(Qt.PointingHandCursor)
        self.new_button.clicked.connect(self.new_session)
        footer.addWidget(self.new_button)
        self.open_button = QPushButton("在主窗打开", objectName="quiet")
        self.open_button.setCursor(Qt.PointingHandCursor)
        self.open_button.clicked.connect(self.open_in_main)
        footer.addWidget(self.open_button)
        box.addLayout(footer)
        self.set_theme(dark)
        self.set_state("idle")
        self.collapse()
        self.render()

    def set_theme(self, dark):
        if dark:
            surface, ink, muted, line, field, accent, tint = (
                "#1e2226", "#f2f3f4", "#a9b3be", "#3a434c", "#272d34", "#9bdcca", "#2f4a45",
            )
        else:
            surface, ink, muted, line, field, accent, tint = (
                "#fcfdfd", "#202c33", "#52616d", "#dbe5e8", "#f1f6f6", "#12675a", "#d7ece6",
            )
        self.ink, self.muted, self.tint, self.surface = ink, muted, tint, surface
        self.setStyleSheet(f"""
            QWidget {{ color: {ink}; font-size: 13px; }}
            QFrame#chatCard, QPushButton#capsule {{ background: {surface}; border: 1px solid {line}; border-radius: 18px; }}
            QPushButton#capsule {{ font-weight: 600; color: {accent}; }}
            QLabel#title {{ font-size: 15px; font-weight: 650; }}
            QLabel#badge, QPushButton#send {{ background: {tint}; color: {accent}; border: 0; border-radius: 8px; padding: 5px 9px; }}
            QLabel#hints, QPushButton#quiet {{ color: {muted}; font-size: 11px; }}
            QPushButton#quiet {{ background: transparent; border: 0; padding: 5px; }}
            QPushButton:focus {{ outline: none; border: 1px solid {accent}; }}
            QPushButton#capsule:hover, QPushButton#quiet:hover {{ background: {tint}; }}
            QPushButton#send:disabled {{ color: {muted}; }}
            QFrame#compose {{ background: {field}; border: 1px solid {line}; border-radius: 11px; }}
            QPlainTextEdit, QTextBrowser {{ background: transparent; border: none; }}
            QTextBrowser {{ padding-right: 6px; selection-background-color: {tint}; }}
            QScrollBar:vertical {{ background: transparent; width: 6px; margin: 0; }}
            QScrollBar::handle:vertical {{ background: {line}; border-radius: 3px; min-height: 24px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        """)
        self.render()

    def position(self):
        screen = self.screen() or QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        width = min(438 if self.expanded else 178, bounds.width())
        height = min(320 if self.expanded else 36, bounds.height())
        self.setFixedSize(width, height)
        self.capsule.setGeometry(0, 0, width, height)
        self.card.setGeometry(0, 0, width, height)
        self.move(bounds.x() + (bounds.width() - width) // 2, bounds.y() + 3)

    def _pin_native(self):
        """非激活浮动面板：点它不把宿主应用切到前台，主窗也不会跟着冒出来。"""
        if self._pinned or sys.platform != "darwin":
            return
        if QApplication.platformName() != "cocoa":
            return
        try:
            import ctypes
            import ctypes.util

            lib = ctypes.CDLL(ctypes.util.find_library("objc"))
            lib.objc_getClass.restype = ctypes.c_void_p
            lib.objc_getClass.argtypes = [ctypes.c_char_p]
            lib.sel_registerName.restype = ctypes.c_void_p
            lib.sel_registerName.argtypes = [ctypes.c_char_p]
            send_ptr = ctypes.cast(lib.objc_msgSend, ctypes.c_void_p).value
            call = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
            call_arg = ctypes.CFUNCTYPE(
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulonglong
            )
            call_uint = ctypes.CFUNCTYPE(ctypes.c_ulonglong, ctypes.c_void_p, ctypes.c_void_p)
            s0, s1, su = call(send_ptr), call_arg(send_ptr), call_uint(send_ptr)
            sel = lib.sel_registerName
            handle = int(self.winId())
            if not handle:
                return
            view = ctypes.c_void_p(handle)
        except Exception:
            return
        try:
            window = s0(view, sel(b"window"))
            if not window:
                return
            s1(window, sel(b"setCanHide:"), 0)
            s1(window, sel(b"setHidesOnDeactivate:"), 0)
            mask = int(su(window, sel(b"styleMask")) or 0)
            s1(window, sel(b"setStyleMask:"), mask | (1 << 7))
            s1(window, sel(b"setFloatingPanel:"), 1)
            self._pinned = True
        except Exception:
            pass

    def _become_key(self):
        """非激活面板也要拿到键盘焦点，否则输入框收不到字。"""
        if sys.platform != "darwin" or QApplication.platformName() != "cocoa":
            return
        try:
            import ctypes
            import ctypes.util

            lib = ctypes.CDLL(ctypes.util.find_library("objc"))
            lib.sel_registerName.restype = ctypes.c_void_p
            lib.sel_registerName.argtypes = [ctypes.c_char_p]
            send_ptr = ctypes.cast(lib.objc_msgSend, ctypes.c_void_p).value
            s0 = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(send_ptr)
            handle = int(self.winId())
            if not handle:
                return
            window = s0(ctypes.c_void_p(handle), lib.sel_registerName(b"window"))
            if window:
                s0(window, lib.sel_registerName(b"makeKeyWindow"))
        except Exception:
            pass

    def expand(self):
        self.expanded = True
        self.capsule.hide()
        self.card.show()
        self.position()
        self.show()
        self._pin_native()
        self._become_key()
        self.raise_()
        self.activateWindow()
        self.input.setFocus(Qt.ShortcutFocusReason)

    def collapse(self):
        self.expanded = False
        self.card.hide()
        self.capsule.show()
        self.position()

    def new_session(self):
        self.chat.shutdown()
        self.transcript = []
        self.current_prompt = ""
        self.partial = ""
        self.set_state("idle")
        self.render()
        self.input.clear()
        self.input.setFocus(Qt.ShortcutFocusReason)

    def _title(self):
        first = self.chat.history[0].get("content", "") if self.chat.history else ""
        text = str(first).strip().replace("\n", " ")[:20]
        return f"快捷对话 · {text}" if text else "快捷对话"

    def open_in_main(self):
        if not self.chat.history:
            self.hints.setText("还没有可打开的对话")
            return
        snapshot = self.chat.snapshot(self._title())
        stage = "能力"
        try:
            from app.plugins.sdk import pool_for

            caps = pool_for(plugin="notch-chat", surface="ui")
            if caps is None:
                raise RuntimeError("没有能力池")
            for name in ("session.persist", "session.history", "session.manage"):
                if name not in caps:
                    raise RuntimeError(f"未获授权 {name}")
            stage = "落库"
            if not caps["session.persist"](snapshot):
                raise RuntimeError("宿主拒绝写入")
            record = caps["session.history"]["session"](snapshot["session_id"]) or {}
            saved = len(record.get("messages") or [])
            if saved != len(snapshot["messages"]):
                raise RuntimeError(f"读回 {saved} 条")
        except Exception as exc:
            logger.warning(f"[notch-chat] 在主窗打开失败（{stage}）: {type(exc).__name__}: {exc}")
            self.hints.setText(f"打开失败于{stage}")
            return
        # 主窗流式时宿主会开新标签页而不加载记录；先停流，等队列落地再加载
        if "session.interrupt" in caps:
            try:
                caps["session.interrupt"]()
            except Exception:
                pass
        self.hints.setText("正在主窗打开…")
        QTimer.singleShot(3000, lambda: self._select_in_main(caps, snapshot))

    def _select_in_main(self, caps, snapshot):
        try:
            manage = caps["session.manage"]
            select = manage["select"] if isinstance(manage, dict) else manage()["select"]
            select(snapshot["session_id"])
        except Exception as exc:
            logger.warning(f"[notch-chat] 加载会话异常: {type(exc).__name__}: {exc}")
            self.hints.setText("打开失败于加载")
            return
        QTimer.singleShot(1200, lambda: self._verify_open(caps, snapshot))

    def _verify_open(self, caps, snapshot):
        try:
            current = caps["session.read"]()
            loaded = str((current or {}).get("session_id") or "")
        except Exception:
            loaded = ""
        if loaded == snapshot["session_id"]:
            logger.info("[notch-chat] 主窗已加载会话")
            self.hints.setText("已在主窗口打开")
        else:
            logger.warning("[notch-chat] 主窗未切换到目标会话，已留在历史里")
            self.hints.setText("已存入主窗历史，可在历史面板打开")

    def hide_panel(self):
        self.collapse()
        self.hide()

    def toggle(self):
        if self.expanded and self.isVisible():
            self.collapse()
        else:
            self.expand()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.expanded:
            self.collapse()
        else:
            super().keyPressEvent(event)

    def set_state(self, state):
        if state == self.state and state == "streaming":
            return
        self.state = state
        label = STATUS[state]
        self.capsule.setText(f"{MARK[state]}  {label}    ⌄")
        self.badge.setText(label)
        self.send.setEnabled(state != "stopping")
        self.send.setText("停止  ■" if state in BUSY else "发送  ↑")
        self.hints.setText(f"↵ 发送   ⇧↵ 换行   ·   {self.hotkey_hint}")

    def tools(self):
        if self._tool_schema is None:
            try:
                from app.plugins.sdk import pool_for

                caps = pool_for(plugin="notch-chat", surface="ui")
                self._tool_schema = list(caps["model.schema"]("") or []) if caps is not None else []
            except Exception:
                self._tool_schema = []
        return self._tool_schema

    def submit(self):
        if self.state in BUSY:
            if self.sender() is self.send:
                self.chat.stop()
            return
        text = self.input.toPlainText().strip()
        if not text:
            return
        if self.chat.send(text, tools=self.tools()):
            self.current_prompt = text
            self.partial = ""
            self.input.clear()
            self.render()

    def append_delta(self, piece):
        if not self.partial:
            self.reply.moveCursor(QTextCursor.End)
        bar = self.reply.verticalScrollBar()
        follow = bar.value() >= bar.maximum() - 4
        self.partial += piece
        cursor = self.reply.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(piece)
        if follow:
            bar.setValue(bar.maximum())

    def finish(self, state, text):
        if self.current_prompt:
            answer = text or self.partial
            if state == "stopped":
                answer = f"{answer}\n［已停止］".strip()
            self.transcript.append((self.current_prompt, answer))
        elif text:
            self.transcript.append(("", text))
        self.current_prompt = ""
        self.partial = ""
        self.render()

    def render(self):
        turns = list(self.transcript)
        if self.current_prompt:
            turns.append((self.current_prompt, self.partial))
        blocks = []
        for question, answer in turns:
            if question:
                bubble = escape(question).replace("\n", "<br>")
                blocks.append(
                    f'<p align="right" style="margin:0 0 10px 0"><span style="background-color:{self.tint}; color:{self.ink}">'
                    f"&nbsp;&nbsp;{bubble}&nbsp;&nbsp;</span></p>"
                )
            if answer == self.partial and self.state in BUSY:
                answer += "▍"
            for para in answer.split("\n\n"):
                if para.strip():
                    body = markdown_html(para).replace(chr(10), "<br>")
                    blocks.append(f'<p style="margin:0 0 9px 0">{body}</p>')
        empty = f'<p style="margin:0; color:{self.muted}">从一个问题开始。<br>这条对话与主窗口分开。</p>'
        self.reply.setHtml(f'<body style="color:{self.ink}">{"".join(blocks) or empty}</body>')
        self.reply.verticalScrollBar().setValue(self.reply.verticalScrollBar().maximum())
