# -*- coding: utf-8 -*-
"""竖向趋势列表 —— 每个请求一行，横向堆叠条表示上下文组成。

用于 Context 面板「趋势」tab 的默认布局：371 个请求不再挤在一条超长横轴里，
而是纵向逐行滚动，阅读顺序与对话推进一致。
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from PyQt5.QtCore import QRect, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from .fmt import fmt_int, fmt_k
from .theme import Palette
from .widgets import clear_layout
from .tooltip import hide_chart_tooltip, show_chart_tooltip


class TrendRow(QWidget):
    clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._palette = Palette()
        self._index = 0
        self._step: Dict[str, Any] = {}
        self._max_input = 1
        self._max_delta = 1
        self._mode = "total"
        self._keys: List[Tuple[str, QColor]] = []
        self._unit = "step"
        self._hover = False
        self._selected = False
        self.setFixedHeight(26)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def set_data(
        self,
        index: int,
        step: Dict[str, Any],
        max_input: int,
        max_delta: int,
        mode: str,
        keys: List[Tuple[str, QColor]],
        unit: str = "step",
    ) -> None:
        self._index = index
        self._step = step
        self._max_input = max(1, int(max_input))
        self._max_delta = max(1, int(max_delta))
        self._mode = mode
        self._keys = keys
        self._unit = unit
        self.update()

    def set_selected(self, selected: bool) -> None:
        if self._selected != selected:
            self._selected = selected
            self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        p = self._palette
        rect = QRectF(0, 1, self.width(), self.height() - 2)
        if self._selected:
            painter.setPen(Qt.NoPen)
            painter.setBrush(p.alpha(p.accent, 26))
            painter.drawRoundedRect(rect, 5, 5)
        elif self._hover:
            painter.setPen(Qt.NoPen)
            painter.setBrush(p.hover_bg)
            painter.drawRoundedRect(rect, 5, 5)

        font = QFont(p.font_family) if p.font_family else QFont()
        font.setPixelSize(max(11, p.font_size - 2))
        painter.setFont(font)
        # 左侧序号
        painter.setPen(QPen(p.text_secondary))
        painter.drawText(QRect(7, 0, 44, self.height()), Qt.AlignLeft | Qt.AlignVCenter, f"#{self._index + 1}")

        # 右侧数值
        input_tokens = int(self._step.get("input", 0) or 0)
        delta = int(self._step.get("delta", 0) or 0)
        right_text = fmt_k(input_tokens)
        if delta:
            right_text += f"  {'+' if delta >= 0 else ''}{fmt_k(delta)}"
        painter.setPen(QPen(p.text_primary))
        painter.drawText(
            QRect(self.width() - 150, 0, 143, self.height()),
            Qt.AlignRight | Qt.AlignVCenter,
            right_text,
        )

        # 横条区域
        bar_left = 54.0
        bar_right = self.width() - 160.0
        bar_w = max(10.0, bar_right - bar_left)
        bar_h = 10.0
        bar_y = (self.height() - bar_h) / 2.0
        track = QRectF(bar_left, bar_y, bar_w, bar_h)
        painter.setPen(Qt.NoPen)
        painter.setBrush(p.alpha(p.border, 40))
        painter.drawRoundedRect(track, 3, 3)

        if self._mode == "delta":
            center = bar_left + bar_w / 2
            value = abs(delta)
            length = (bar_w / 2 - 2) * value / self._max_delta
            color = p.accent if delta >= 0 else QColor("#f87171")
            if delta >= 0:
                bar = QRectF(center, bar_y, max(1.0, length), bar_h)
            else:
                bar = QRectF(center - max(1.0, length), bar_y, max(1.0, length), bar_h)
            painter.setBrush(p.alpha(color, 210))
            painter.drawRoundedRect(bar, 2, 2)
            painter.setPen(QPen(p.alpha(p.border, 160), 1))
            painter.drawLine(int(center), int(bar_y - 1), int(center), int(bar_y + bar_h + 1))
        else:
            total_w = max(1.0, bar_w * input_tokens / self._max_input)
            comp = self._step.get("composition") or {}
            x = bar_left
            for key, color in self._keys:
                value = int(comp.get(key, 0) or 0)
                if value <= 0:
                    continue
                seg_w = total_w * value / max(1, input_tokens)
                if seg_w <= 0:
                    continue
                painter.setBrush(QBrush(color))
                painter.drawRect(QRectF(x, bar_y, seg_w + 0.3, bar_h))
                x += seg_w

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        step = self._step
        title = "Turn" if self._unit == "turn" else "Step"
        parts = [
            f"{title} #{self._index + 1} · {step.get('ts', '')}",
            f"上下文 ≈ {fmt_int(step.get('input', 0))} tokens",
            f"输出 {fmt_int(step.get('output', 0))} tokens",
        ]
        delta = int(step.get("delta", 0) or 0)
        if delta:
            parts.append(f"变化 {'+' if delta >= 0 else ''}{fmt_int(delta)}")
        show_chart_tooltip(self, event.globalPos(), "\n".join(parts), self._palette)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        hide_chart_tooltip()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.clicked.emit(self._index)
        super().mousePressEvent(event)


class TrendList(QWidget):
    """纵向逐请求列表。"""

    stepClicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._palette = Palette()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(1)
        self._rows: List[TrendRow] = []
        self._selected = -1
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        for row in self._rows:
            row.set_palette_obj(palette)

    def set_data(
        self,
        steps: List[Dict[str, Any]],
        keys: List[Tuple[str, QColor]],
        mode: str,
        unit: str = "step",
        reverse: bool = True,
    ) -> None:
        clear_layout(self._layout)
        self._rows = []
        max_input = max((int(s.get("input", 0) or 0) for s in steps), default=1) or 1
        max_delta = max((abs(int(s.get("delta", 0) or 0)) for s in steps), default=1) or 1
        # 上限保护：极端长会话只保留最近 800 个请求，避免一次建上万行
        limit = 800
        base = steps[-limit:] if len(steps) > limit else list(steps)
        offset = len(steps) - len(base)
        items = list(enumerate(base, start=offset))
        if reverse:
            items.reverse()
        for _i, (original_index, step) in enumerate(items):
            row = TrendRow(self)
            row.set_palette_obj(self._palette)
            row.set_data(original_index, step, max_input, max_delta, mode, keys, unit)
            row.clicked.connect(self._on_clicked)
            self._layout.addWidget(row)
            self._rows.append(row)
        if self._selected < offset or self._selected >= len(steps):
            self._selected = -1
        for row in self._rows:
            row.set_selected(row._index == self._selected)

    def _on_clicked(self, index: int) -> None:
        self.set_selected(index)
        self.stepClicked.emit(index)

    def set_selected(self, index: int) -> None:
        self._selected = index
        for row in self._rows:
            row.set_selected(row._index == index)
