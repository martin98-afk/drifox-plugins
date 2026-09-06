# -*- coding: utf-8 -*-
"""录音状态浮窗：屏幕右下角，红点脉冲 + 计时 + 取消键。

两态：recording（红点脉冲计时）→ recognizing（「识别中…」，按钮禁用）。
点浮窗主体 = 停止并识别（stop_requested）；取消键 / Esc = 丢弃（cancelled）。
WA_DeleteOnClose 防窗体残留；Tool 样式不进任务栏。
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

# 深色卡片配色（浮窗独立于主题，固定深色即可）
_BG = QColor(43, 43, 43, 242)
_TXT = "#e0e0e0"
_DIM = "#9a9a9a"
_DOT_ON = "#ff4d4f"
_DOT_OFF = "#7a2a2b"

# 刷新节奏
_TICK_MS = 1000
_PULSE_MS = 500


class RecordingOverlay(QWidget):
    """录音/识别状态浮窗。信号只负责请求，实际状态切换由上层驱动。"""

    stop_requested = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self):
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool,  # type: ignore[arg-type]
        )
        self.setAttribute(Qt.WA_DeleteOnClose)
        self._elapsed = 0
        self._recognizing = False

        self.setStyleSheet(
            f"background-color: rgba(43,43,43,242); border-radius: 10px; color: {_TXT};"
        )
        self.setFixedSize(230, 64)

        # 红点脉冲：两档颜色交替
        self._dot = QLabel("●")
        self._dot.setStyleSheet(
            f"color: {_DOT_ON}; font-size: 20px; border: none; background: transparent;"
        )

        self._timer_label = QLabel("0:00")
        self._timer_label.setStyleSheet(
            f"color: {_TXT}; font-size: 18px; font-weight: bold; border: none; background: transparent;"
        )

        self._status_label = QLabel("正在聆听")
        self._status_label.setStyleSheet(
            f"color: {_DIM}; font-size: 12px; border: none; background: transparent;"
        )

        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_btn.setStyleSheet(
            "QPushButton { color: #d0d0d0; background: #3a3a3a; border: none;"
            " border-radius: 6px; padding: 5px 14px; font-size: 12px; }"
            "QPushButton:hover { background: #4a4a4a; }"
        )
        self._cancel_btn.clicked.connect(self._emit_cancel)

        mid = QHBoxLayout()
        mid.setSpacing(10)
        mid.addWidget(self._dot)
        mid.addWidget(self._timer_label)
        mid.addStretch(1)
        mid.addWidget(self._status_label)
        mid.addStretch(1)
        mid.addWidget(self._cancel_btn)
        self.setLayout(mid)

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._on_tick)
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._on_pulse)
        self._pulse_state = True

    # ── 生命周期 ──

    def start_recording(self) -> None:
        """进入录音态：归零计时，启动节奏定时器，钉到屏幕右下角。"""
        self._elapsed = 0
        self._recognizing = False
        self._timer_label.setText("0:00")
        self._status_label.setText("正在聆听")
        self._cancel_btn.setEnabled(True)
        self._tick_timer.start(_TICK_MS)
        self._pulse_timer.start(_PULSE_MS)
        self._place_bottom_right()
        self.show()

    def enter_recognizing(self) -> None:
        """进入识别态：停计时与脉冲，禁用取消（识别只有数秒）。"""
        self._recognizing = True
        self._tick_timer.stop()
        self._pulse_timer.stop()
        self._dot.setStyleSheet(
            f"color: {_DOT_OFF}; font-size: 20px; border: none; background: transparent;"
        )
        self._status_label.setText("识别中…")
        self._cancel_btn.setEnabled(False)

    def set_status(self, text: str) -> None:
        """识别期间更新状态文案（如「下载模型中…」），识别态之外忽略。"""
        if self._recognizing:
            self._status_label.setText(text)

    # ── 定时器槽 ──

    def _on_tick(self) -> None:
        self._elapsed += 1
        self._timer_label.setText(f"{self._elapsed // 60}:{self._elapsed % 60:02d}")

    def _on_pulse(self) -> None:
        self._pulse_state = not self._pulse_state
        color = _DOT_ON if self._pulse_state else _DOT_OFF
        self._dot.setStyleSheet(
            f"color: {color}; font-size: 20px; border: none; background: transparent;"
        )

    # ── 交互 ──

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and not self._recognizing:
            self.stop_requested.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self._emit_cancel()
            event.accept()
            return
        super().keyPressEvent(event)

    def _emit_cancel(self) -> None:
        if self._recognizing:
            return
        self.cancelled.emit()
        self.close()

    # ── 位置 ──

    def _place_bottom_right(self) -> None:
        from PyQt5.QtWidgets import QApplication

        screen = QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        margin = 40
        self.move(
            avail.right() - self.width() - margin,
            avail.bottom() - self.height() - margin,
        )
