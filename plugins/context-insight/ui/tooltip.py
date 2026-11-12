# -*- coding: utf-8 -*-
"""图表自绘提示框 —— 替代原生 QToolTip。

原生 QToolTip 在 macOS 上由系统绘制，palette 里的 ToolTipBase 不一定生效，
实测会出现“透明底 + 白字 + 白边”，压在深色卡片上完全看不清。这里用
``Qt.ToolTip`` 顶层窗口 + 主题色 QFrame 自绘，保证任何主题下都有实底。
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout, QWidget

from .theme import Palette
from .widgets import css

_TOOLTIP: Optional["ChartTooltip"] = None


class ChartTooltip(QWidget):
    def __init__(self):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._bg = QColor(30, 34, 42, 245)
        self._border = QColor(255, 255, 255, 40)
        self._frame = QFrame(self)
        self._frame.setObjectName("ciChartTooltip")
        self._frame.setStyleSheet("background: transparent;")
        self._label = QLabel(self._frame)
        self._label.setTextFormat(Qt.PlainText)
        self._label.setWordWrap(False)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)
        inner = QVBoxLayout(self._frame)
        inner.setContentsMargins(11, 8, 11, 8)
        inner.addWidget(self._label)
        self.hide()

    def paintEvent(self, _event) -> None:  # noqa: N802
        # 顶层透明窗口自己画圆角实底，避免 QFrame 样式在部分平台不落色
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(self._bg)
        painter.setPen(QPen(self._border, 1))
        painter.drawRoundedRect(rect, 8, 8)

    def show_text(self, global_pos: QPoint, text: str, palette: Palette) -> None:
        self._bg = QColor(palette.card_bg)
        self._bg.setAlpha(245)
        self._border = QColor(palette.alpha(palette.border, 210))
        self._label.setStyleSheet(
            f"color: {css(palette.text_primary)}; background: transparent; font-size: {palette.fs(-1)}px;"
        )
        self._label.setText(text)
        self.adjustSize()
        pos = global_pos + QPoint(14, 16)
        screen = QApplication.screenAt(global_pos) or QApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            if pos.x() + self.width() > geo.right():
                pos.setX(global_pos.x() - self.width() - 10)
            if pos.y() + self.height() > geo.bottom():
                pos.setY(global_pos.y() - self.height() - 10)
        self.move(pos)
        self.show()
        self.raise_()


def show_chart_tooltip(widget: QWidget, global_pos: QPoint, text: str, palette: Palette) -> None:
    global _TOOLTIP
    if _TOOLTIP is None:
        _TOOLTIP = ChartTooltip()
    _TOOLTIP.show_text(global_pos, text, palette)


def hide_chart_tooltip() -> None:
    if _TOOLTIP is not None:
        _TOOLTIP.hide()


def destroy_chart_tooltip() -> None:
    global _TOOLTIP
    if _TOOLTIP is not None:
        _TOOLTIP.hide()
        _TOOLTIP.deleteLater()
        _TOOLTIP = None
