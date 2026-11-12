# -*- coding: utf-8 -*-
"""通用 UI 组件 —— 卡片、KPI、分段控件、图例、台账行、流式布局。"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from PyQt5.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .fmt import fmt_int, fmt_pct
from .theme import Palette


def css(color: QColor) -> str:
    return f"rgba({color.red()},{color.green()},{color.blue()},{color.alpha()})"


def css_html(color: QColor) -> str:
    """HTML/CSS 用：alpha 为 0~1（QSS 用 css() 的 0~255 会失效）。"""
    return f"rgba({color.red()},{color.green()},{color.blue()},{color.alpha() / 255:.3f})"


def repolish(widget: QWidget) -> None:
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


class FlowLayout(QLayout):
    """自动换行布局（Qt 官方示例的轻量实现）。"""

    def __init__(self, parent=None, margin: int = 0, h_spacing: int = 8, v_spacing: int = 8):
        super().__init__(parent)
        self._items: List[Any] = []
        self._h = h_spacing
        self._v = v_spacing
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):  # noqa: N802
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._h
            if next_x - self._h > effective.right() and line_height > 0:
                x = effective.x()
                y = y + line_height + self._v
                next_x = x + hint.width() + self._h
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()


class SectionCard(QFrame):
    """带标题的内容卡。"""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("ciSectionCard")
        self._palette = Palette()
        self._title = title
        self._subtitle = ""
        self._header = QWidget(self)
        self._header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._header_layout = QHBoxLayout(self._header)
        self._header_layout.setContentsMargins(0, 0, 0, 0)
        self._header_layout.setSpacing(8)
        self._title_label = QLabel(title, self._header)
        self._subtitle_label = QLabel("", self._header)
        self._subtitle_label.setObjectName("ciSectionSub")
        self._header_layout.addWidget(self._title_label)
        self._header_layout.addWidget(self._subtitle_label)
        self._header_layout.addStretch(1)
        self._body = QWidget(self)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(8)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(self._header)
        layout.addWidget(self._body, 1)
        self._apply_style()

    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        self._apply_style()
        for child in self.findChildren(QWidget):
            child.update()

    def _apply_style(self) -> None:
        p = self._palette
        self.setStyleSheet(
            f"#ciSectionCard {{ background: {css(p.card_bg)}; border: 1px solid {css(p.alpha(p.border, 180))};"
            f" border-radius: 12px; }}"
            f"#ciSectionCard QLabel {{ color: {css(p.text_primary)}; background: transparent; }}"
            f"#ciSectionCard QLabel#ciSectionSub {{ color: {css(p.text_secondary)}; font-size: {p.fs(-2)}px; }}"
        )
        font = QFont(p.font_family) if p.font_family else QFont()
        font.setPixelSize(max(11, p.font_size))
        font.setBold(True)
        self._title_label.setFont(font)
        sub_font = QFont(font)
        sub_font.setBold(False)
        sub_font.setPixelSize(max(10, p.font_size - 2))
        self._subtitle_label.setFont(sub_font)

    def set_title(self, title: str) -> None:
        self._title = title
        self._title_label.setText(title)

    def set_subtitle(self, text: str) -> None:
        self._subtitle = text
        self._subtitle_label.setText(text)

    def header_layout(self) -> QHBoxLayout:
        return self._header_layout

    def body_layout(self) -> QVBoxLayout:
        return self._body_layout

    def add_widget(self, widget: QWidget, stretch: int = 0) -> None:
        self._body_layout.addWidget(widget, stretch)

    def add_layout(self, layout) -> None:
        self._body_layout.addLayout(layout)

    def add_stretch(self) -> None:
        self._body_layout.addStretch(1)


class KpiCard(QFrame):
    """KPI 数值卡。"""

    clicked = pyqtSignal()

    def __init__(self, label: str, value: str = "—", sub: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("ciKpiCard")
        self.setCursor(Qt.PointingHandCursor)
        self._palette = Palette()
        self._label = QLabel(label, self)
        self._label.setObjectName("ciKpiLabel")
        self._value = QLabel(value, self)
        self._value.setObjectName("ciKpiValue")
        self._sub = QLabel(sub, self)
        self._sub.setObjectName("ciKpiSub")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(3)
        layout.addWidget(self._label)
        layout.addWidget(self._value)
        layout.addWidget(self._sub)
        self.setMinimumHeight(88)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._apply_style()

    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        self.setMinimumHeight(max(88, palette.fs(0) * 3 + 30))
        self._apply_style()

    def _apply_style(self) -> None:
        p = self._palette
        self.setStyleSheet(
            f"#ciKpiCard {{ background: {css(p.card_bg)}; border: 1px solid {css(p.alpha(p.border, 160))};"
            f" border-radius: 12px; }}"
            f"#ciKpiCard:hover {{ border: 1px solid {css(p.alpha(p.accent, 190))}; }}"
            f"#ciKpiLabel {{ color: {css(p.text_secondary)}; background: transparent; }}"
            f"#ciKpiValue {{ color: {css(p.text_primary)}; background: transparent; }}"
            f"#ciKpiSub {{ color: {css(p.text_secondary)}; background: transparent; }}"
        )
        base = QFont(p.font_family) if p.font_family else QFont()
        label_font = QFont(base)
        label_font.setPixelSize(max(11, p.font_size - 1))
        self._label.setFont(label_font)
        value_font = QFont(base)
        value_font.setPixelSize(max(18, p.font_size + 8))
        value_font.setBold(True)
        self._value.setFont(value_font)
        sub_font = QFont(base)
        sub_font.setPixelSize(max(10, p.font_size - 2))
        self._sub.setFont(sub_font)

    def set_value(self, value: str, sub: str = "") -> None:
        self._value.setText(value)
        if sub:
            self._sub.setText(sub)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.clicked.emit()
        super().mousePressEvent(event)


class Pill(QLabel):
    """小型胶囊标签。"""

    def __init__(self, text: str = "", parent=None, color: Optional[QColor] = None):
        super().__init__(text, parent)
        self._palette = Palette()
        self._color = color or self._palette.accent
        self.setAlignment(Qt.AlignCenter)
        self._apply_style()

    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        if self._color == Palette().accent:
            self._color = palette.accent
        self._apply_style()

    def set_color(self, color: QColor) -> None:
        self._color = color
        self._apply_style()

    def _apply_style(self) -> None:
        p = self._palette
        self.setStyleSheet(
            f"color: {css(p.text_primary)}; background: {css(p.alpha(self._color, 46))};"
            f" border: 1px solid {css(p.alpha(self._color, 110))}; border-radius: 8px;"
            f" padding: 1px 7px; font-size: {p.fs(-2)}px;"
        )


class SegmentedControl(QWidget):
    """分段切换控件。"""

    changed = pyqtSignal(str)

    def __init__(self, options: List[Tuple[str, str]], current: str = "", parent=None):
        super().__init__(parent)
        self._palette = Palette()
        self._buttons: Dict[str, QPushButton] = {}
        self._current = current or (options[0][0] if options else "")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        for key, label in options:
            btn = QPushButton(label, self)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self.set_current(k, emit=True))
            layout.addWidget(btn)
            self._buttons[key] = btn
        layout.addStretch(1)
        self._apply_style()

    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        self._apply_style()

    def set_current(self, key: str, emit: bool = False) -> None:
        if key not in self._buttons:
            return
        self._current = key
        for k, btn in self._buttons.items():
            btn.setChecked(k == key)
        self._apply_style()
        if emit:
            self.changed.emit(key)

    def current(self) -> str:
        return self._current

    def _apply_style(self) -> None:
        p = self._palette
        self.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {css(p.text_secondary)}; border: none;"
            f" border-radius: 7px; padding: 4px 10px; font-size: {p.fs(-1)}px; }}"
            f"QPushButton:hover {{ background: {css(p.hover_bg)}; color: {css(p.text_primary)}; }}"
            f"QPushButton:checked {{ background: {css(p.alpha(p.accent, 40))}; color: {css(p.text_primary)};"
            f" border: 1px solid {css(p.alpha(p.accent, 120))}; }}"
        )
        for k, btn in self._buttons.items():
            btn.setChecked(k == self._current)


class LegendList(QWidget):
    """图例行：色点 + 名称 + 数值 + 百分比。"""

    rowClicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._palette = Palette()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._rows: List[QWidget] = []
        self._data: List[Tuple[str, str, int, QColor]] = []

    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        self.set_data(self._data)

    def set_data(self, rows: Iterable[Tuple[str, str, int, QColor]], total: Optional[int] = None) -> None:
        self._data = [(k, label, max(0, int(v)), c) for k, label, v, c in rows]
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()
        total = total if total is not None else sum(v for _, _, v, _ in self._data)
        for key, label, value, color in self._data:
            row = _LegendRow(key, label, value, color, total, self._palette, self)
            row.clicked.connect(self.rowClicked)
            self._layout.addWidget(row)
        self._layout.addStretch(1)


class LegendChips(QWidget):
    """横向图例：色点 + 名称，自动换行（趋势图/堆叠图用）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._palette = Palette()
        self._flow = FlowLayout(self, 0, 10, 4)
        self.setLayout(self._flow)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        self.set_data(self._data)

    _data: List[Tuple[str, QColor]] = []

    def set_data(self, rows: Iterable[Tuple[str, QColor]]) -> None:
        self._data = list(rows)
        while self._flow.count():
            item = self._flow.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()
        for label, color in self._data:
            chip = QLabel(label, self)
            chip.setStyleSheet(
                f"color: {css(self._palette.text_secondary)}; font-size: {self._palette.fs(-2)}px;"
                f" background: transparent; padding: 1px 0;"
            )
            dot = "●"
            chip.setText(f"<span style='color:{css_html(color)}'>{dot}</span> {label}")
            chip.setTextFormat(Qt.RichText)
            self._flow.addWidget(chip)


class _LegendRow(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, key: str, label: str, value: int, color: QColor, total: int, palette: Palette, parent=None):
        super().__init__(parent)
        self.setObjectName("ciLegendRow")
        self.setCursor(Qt.PointingHandCursor)
        self._key = key
        self._palette = palette
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(7)
        dot = QLabel(self)
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background: {css(color)}; border-radius: 4px;")
        name = QLabel(label, self)
        name.setStyleSheet(f"color: {css(palette.text_primary)}; font-size: {palette.fs(-1)}px; background: transparent;")
        amount = QLabel(f"{fmt_int(value)}", self)
        amount.setStyleSheet(f"color: {css(palette.text_secondary)}; font-size: {palette.fs(-2)}px; background: transparent;")
        pct = QLabel(fmt_pct(value / total * 100 if total else 0, 1), self)
        pct.setFixedWidth(44)
        pct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        pct.setStyleSheet(f"color: {css(palette.text_secondary)}; font-size: {palette.fs(-2)}px; background: transparent;")
        layout.addWidget(dot)
        layout.addWidget(name, 1)
        layout.addWidget(amount)
        layout.addWidget(pct)
        self.setStyleSheet(f"#ciLegendRow:hover {{ background: {css(palette.hover_bg)}; border-radius: 5px; }}")

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.clicked.emit(self._key)
        super().mousePressEvent(event)


class BarRow(QWidget):
    """台账行：名称 + 横条 + 计数（可点击筛选）。"""

    clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._palette = Palette()
        self._name = ""
        self._count = 0
        self._max = 1
        self._color = self._palette.accent
        self.setMinimumHeight(24)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)

    def set_data(self, name: str, count: int, max_count: int, color: QColor, palette: Optional[Palette] = None) -> None:
        self._name = name
        self._count = max(0, int(count))
        self._max = max(1, int(max_count))
        self._color = color
        if palette is not None:
            self._palette = palette
        self.setMinimumHeight(max(24, self._palette.fs(0) + 8))
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        p = self._palette
        font = QFont(p.font_family) if p.font_family else QFont()
        font.setPixelSize(max(11, p.font_size))
        fm = QFontMetrics(font)
        # 名称列固定占 45%（上限 180px）：短名称不被硬压，长名称按列宽省略
        name_w = max(64.0, min(self.width() * 0.45, 180.0))
        name_rect = QRect(0, 0, int(name_w), self.height())
        painter.setPen(QPen(p.text_primary))
        painter.setFont(font)
        name_text = fm.elidedText(self._name, Qt.ElideRight, max(8, int(name_w)))
        painter.drawText(name_rect, Qt.AlignLeft | Qt.AlignVCenter, name_text)
        # 计数
        count_text = f"{self._count:,}"
        count_w = fm.horizontalAdvance(count_text) + 6
        painter.setPen(QPen(p.text_secondary))
        painter.drawText(
            QRect(self.width() - int(count_w), 0, int(count_w), self.height()),
            Qt.AlignRight | Qt.AlignVCenter,
            count_text,
        )
        # 横条
        track_x = name_w + 10
        track_w = max(10.0, self.width() - track_x - count_w - 8)
        track_y = self.height() / 2 - 2
        painter.fillRect(
            QRect(int(track_x), int(track_y), int(track_w), 4),
            p.alpha(p.border, 55),
        )
        ratio = min(1.0, self._count / self._max)
        painter.fillRect(
            QRect(int(track_x), int(track_y), int(track_w * ratio), 4),
            p.alpha(self._color, 210),
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._name:
            self.clicked.emit(self._name)
        super().mousePressEvent(event)


class ElidedLabel(QLabel):
    """按可用像素宽度省略的单行标签（中文标题不糊、不撑破卡片）。"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full_text = text
        self.setText(text)
        self.setWordWrap(False)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

    def set_full_text(self, text: str) -> None:
        self._full_text = text or ""
        self._refresh()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        width = max(10, self.width())
        self.setText(self.fontMetrics().elidedText(self._full_text, Qt.ElideRight, width))


class EmptyState(QWidget):
    def __init__(self, text: str = "暂无数据", parent=None):
        super().__init__(parent)
        parent_palette = getattr(parent, "_palette", None)
        self._palette = parent_palette if isinstance(parent_palette, Palette) else Palette()
        self._label = QLabel(text, self)
        self._label.setAlignment(Qt.AlignCenter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 26, 12, 26)
        layout.addWidget(self._label)
        self.set_palette_obj(self._palette)

    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        self._label.setStyleSheet(f"color: {css(palette.text_secondary)}; font-size: {palette.fs(-1)}px; background: transparent;")

    def set_text(self, text: str) -> None:
        self._label.setText(text)


class TabStrip(QWidget):
    """横向文字 tab。"""

    changed = pyqtSignal(str)

    def __init__(self, items: List[Tuple[str, str]], current: str = "", parent=None):
        super().__init__(parent)
        self._palette = Palette()
        self._buttons: Dict[str, QPushButton] = {}
        self._current = current or (items[0][0] if items else "")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        for key, label in items:
            btn = QPushButton(label, self)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self.set_current(k, emit=True))
            self._layout.addWidget(btn)
            self._buttons[key] = btn
        self._layout.addStretch(1)
        self._apply_style()

    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        self._apply_style()

    def set_current(self, key: str, emit: bool = False) -> None:
        if key not in self._buttons:
            return
        self._current = key
        for k, btn in self._buttons.items():
            btn.setChecked(k == key)
        self._apply_style()
        if emit:
            self.changed.emit(key)

    def current(self) -> str:
        return self._current

    def _apply_style(self) -> None:
        p = self._palette
        self.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {css(p.text_secondary)}; border: none;"
            f" border-bottom: 2px solid transparent; padding: 5px 9px; font-size: {p.fs(-1)}px; }}"
            f"QPushButton:hover {{ color: {css(p.text_primary)}; }}"
            f"QPushButton:checked {{ color: {css(p.text_primary)}; border-bottom: 2px solid {css(p.accent)}; }}"
        )
        for k, btn in self._buttons.items():
            btn.setChecked(k == self._current)


def make_label(text: str, palette: Palette, size_delta: int = 0, bold: bool = False, secondary: bool = False) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f"color: {css(palette.text_secondary if secondary else palette.text_primary)}; background: transparent;"
    )
    font = QFont(palette.font_family) if palette.font_family else QFont()
    font.setPixelSize(max(9, palette.font_size + size_delta))
    font.setBold(bold)
    label.setFont(font)
    return label


def hline(palette: Palette) -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {css(palette.alpha(palette.border, 120))}; border: none;")
    return line
