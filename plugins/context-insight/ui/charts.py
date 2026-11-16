# -*- coding: utf-8 -*-
"""自绘图表控件 —— 环形图 / 堆叠条 / 柱状图 / 热力图 / 趋势图 / 占用环。

全部走 QPainter，颜色由 ``Palette`` 提供，深浅主题由父级 refresh_theme 重刷。
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Tuple

from PyQt5.QtCore import QPoint, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt5.QtWidgets import QSizePolicy, QWidget

from .fmt import fmt_cost, fmt_int, fmt_k
from .theme import Palette
from .tooltip import hide_chart_tooltip, show_chart_tooltip


def _font(palette: Palette, size: int = 0, bold: bool = False) -> QFont:
    font = QFont(palette.font_family) if palette.font_family else QFont()
    font.setPixelSize(max(9, size or palette.font_size))
    font.setBold(bold)
    return font


def _draw_text(
    painter: QPainter,
    rect: QRectF,
    text: str,
    color: QColor,
    palette: Palette,
    size: int = 0,
    bold: bool = False,
    align: int = Qt.AlignLeft | Qt.AlignVCenter,
) -> None:
    painter.setPen(QPen(color))
    painter.setFont(_font(palette, size, bold))
    painter.drawText(rect, align, text)


def _axis_left(palette: Palette, texts: Iterable[str], size: int, base: float = 44.0) -> float:
    """按最宽刻度文本实测宽度算左边距。

    写死左边距会把大数值裁掉：标签框宽 = left - 8，44 只剩 36px，
    "148.8M" 在 9px 字号下会从左侧溢出可视区（7 日用量实测）。
    base 保留为历史下限，避免小区间时留白突变。
    """
    fm = QFontMetrics(_font(palette, size))
    widest = max((fm.horizontalAdvance(t) for t in texts), default=0)
    return max(base, float(widest) + 12.0)

def _rounded_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


class DonutChart(QWidget):
    """环形组成图，中心显示总量 / 标题。"""

    segmentClicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._palette = Palette()
        self._segments: List[Tuple[str, str, int, QColor]] = []
        self._center_title = ""
        self._center_sub = ""
        self._hover = -1
        self.setMouseTracking(True)
        self.setMinimumSize(180, 180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def set_data(
        self,
        segments: Iterable[Tuple[str, str, int, QColor]],
        center_title: str = "",
        center_sub: str = "",
    ) -> None:
        self._segments = [(k, label, max(0, int(v)), c) for k, label, v, c in segments if v > 0]
        self._center_title = center_title
        self._center_sub = center_sub
        self._hover = -1
        self.update()

    def _geometry(self) -> Tuple[QRectF, float]:
        side = min(self.width(), self.height()) - 18
        side = max(40, side)
        rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        thickness = max(9.0, side * 0.15)
        inner = rect.adjusted(thickness, thickness, -thickness, -thickness)
        return inner, thickness

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        inner, thickness = self._geometry()
        outer = inner.adjusted(-thickness, -thickness, thickness, thickness)
        track = QPen(self._palette.track, thickness)
        track.setCapStyle(Qt.FlatCap)
        painter.setPen(track)
        painter.drawArc(outer, 0, 360 * 16)

        total = sum(v for _, _, v, _ in self._segments)
        if total <= 0:
            _draw_text(
                painter,
                inner,
                "暂无数据",
                self._palette.text_secondary,
                self._palette,
                self._palette.fs(-1, 10),
                align=Qt.AlignCenter,
            )
            return

        start = 90 * 16
        for i, (_key, _label, value, color) in enumerate(self._segments):
            span = -int(360 * 16 * value / total)
            if len(self._segments) > 1 and abs(span) > 4 * 16:
                # 固定 1° 间隙：小分类不再被吃掉三分之一
                gap = min(abs(span) // 5, 1 * 16)
                span = span + gap if span < 0 else span - gap
            pen = QPen(color if i != self._hover else color.lighter(115), thickness)
            pen.setCapStyle(Qt.FlatCap)
            painter.setPen(pen)
            painter.drawArc(outer, start, span)
            start += -int(360 * 16 * value / total)

        _draw_text(
            painter,
            QRectF(inner.x(), inner.y() + inner.height() * 0.30, inner.width(), 26),
            self._center_title,
            self._palette.text_primary,
            self._palette,
            max(13, int(inner.width() * 0.11)),
            bold=True,
            align=Qt.AlignCenter,
        )
        if self._center_sub:
            _draw_text(
                painter,
                QRectF(inner.x(), inner.y() + inner.height() * 0.30 + 24, inner.width(), 18),
                self._center_sub,
                self._palette.text_secondary,
                self._palette,
                max(10, int(inner.width() * 0.065)),
                align=Qt.AlignCenter,
            )

    def _hit(self, pos: QPoint) -> int:
        total = sum(v for _, _, v, _ in self._segments)
        if total <= 0:
            return -1
        center = self.rect().center()
        dx = pos.x() - center.x()
        dy = center.y() - pos.y()
        angle = (math.degrees(math.atan2(dy, dx)) + 360) % 360
        # 顶部为 0，顺时针
        angle = (90 - angle) % 360
        acc = 0.0
        for i, (_k, _l, value, _c) in enumerate(self._segments):
            span = 360.0 * value / total
            if acc <= angle < acc + span:
                return i
            acc += span
        return -1

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        idx = self._hit(event.pos())
        if idx != self._hover:
            self._hover = idx
            self.update()
        if idx >= 0:
            _key, label, value, _color = self._segments[idx]
            total = sum(v for _, _, v, _ in self._segments) or 1
            show_chart_tooltip(self, event.globalPos(), f"{label}\n{fmt_int(value)} tokens · {value / total * 100:.1f}%", self._palette)
        else:
            hide_chart_tooltip()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        idx = self._hit(event.pos())
        if idx >= 0:
            self.segmentClicked.emit(self._segments[idx][0])
        super().mousePressEvent(event)


class StackedBar(QWidget):
    """水平堆叠组成条（可带尾部预留段）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._palette = Palette()
        self._segments: List[Tuple[str, str, int, QColor]] = []
        self._reserved: List[Tuple[str, int, QColor]] = []
        self._hover = -1
        self.setMouseTracking(True)
        self.setFixedHeight(18)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def set_data(
        self,
        segments: Iterable[Tuple[str, str, int, QColor]],
        reserved: Optional[Iterable[Tuple[str, int, QColor]]] = None,
    ) -> None:
        self._segments = [(k, label, max(0, int(v)), c) for k, label, v, c in segments if v > 0]
        self._reserved = [(label, max(0, int(v)), c) for label, v, c in (reserved or []) if v > 0]
        self._hover = -1
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(0, 0, max(1, self.width()), max(1, self.height()))
        path = _rounded_path(rect, self.height() / 2)
        painter.setClipPath(path)
        painter.fillRect(rect, self._palette.track)
        total = sum(v for _, _, v, _ in self._segments) + sum(v for _, v, _ in self._reserved)
        if total <= 0:
            painter.end()
            return
        x = 0.0
        for i, (_key, _label, value, color) in enumerate(self._segments):
            width = rect.width() * value / total
            painter.fillRect(QRectF(x, 0, width + 0.5, rect.height()), color)
            x += width
        # 预留段：斜线纹理
        for label, value, color in self._reserved:
            width = rect.width() * value / total
            area = QRectF(x, 0, width + 0.5, rect.height())
            painter.fillRect(area, self._palette.alpha(color, 60))
            pen = QPen(self._palette.alpha(color, 160), 1)
            painter.setPen(pen)
            step = 6
            left = int(area.left())
            for offset in range(0, int(area.width()) + int(area.height()) + step, step):
                painter.drawLine(
                    left + offset,
                    int(area.bottom()),
                    left + offset - int(area.height()),
                    int(area.top()),
                )
            x += width
        painter.end()

    def _hit(self, x: float) -> int:
        total = sum(v for _, _, v, _ in self._segments) + sum(v for _, v, _ in self._reserved)
        if total <= 0:
            return -1
        acc = 0.0
        for i, (_k, _l, value, _c) in enumerate(self._segments):
            width = self.width() * value / total
            if acc <= x < acc + width:
                return i
            acc += width
        return -1

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        idx = self._hit(event.pos().x())
        if idx != self._hover:
            self._hover = idx
            self.update()
        if idx >= 0:
            _key, label, value, _color = self._segments[idx]
            total = sum(v for _, _, v, _ in self._segments) + sum(v for _, v, _ in self._reserved) or 1
            show_chart_tooltip(self, event.globalPos(), f"{label}\n{fmt_int(value)} tokens · {value / total * 100:.1f}%", self._palette)
        else:
            hide_chart_tooltip()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = -1
        self.update()
        super().leaveEvent(event)


class BarChart(QWidget):
    """双序列柱状图：主柱 token，副序列（成本）用折线点。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._palette = Palette()
        self._labels: List[str] = []
        self._values: List[int] = []
        self._costs: List[float] = []
        self._hover = -1
        self.setMouseTracking(True)
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def set_data(self, labels: List[str], values: List[int], costs: Optional[List[float]] = None) -> None:
        self._labels = list(labels)
        self._values = [max(0, int(v)) for v in values]
        self._costs = list(costs or [])
        self._hover = -1
        self.update()

    def _left_margin(self) -> float:
        max_value = max(self._values or [0]) or 1
        return _axis_left(
            self._palette,
            [fmt_k(max_value * i / 4) for i in range(5)],
            self._palette.fs(-4, 9),
        )

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        left, right, top, bottom = self._left_margin(), 12, 16, 26
        plot = QRectF(left, top, max(10, self.width() - left - right), max(10, self.height() - top - bottom))
        max_value = max(self._values or [0]) or 1
        # 网格 + 左侧刻度
        for i in range(5):
            y = plot.bottom() - plot.height() * i / 4
            painter.setPen(QPen(self._palette.alpha(self._palette.border, 70), 1, Qt.DashLine))
            painter.drawLine(QPoint(int(plot.left()), int(y)), QPoint(int(plot.right()), int(y)))
            _draw_text(
                painter,
                QRectF(0, y - 9, left - 8, 18),
                fmt_k(max_value * i / 4),
                self._palette.text_secondary,
                self._palette,
                self._palette.fs(-4, 9),
                align=Qt.AlignRight | Qt.AlignVCenter,
            )

        n = len(self._values)
        if n == 0:
            _draw_text(
                painter,
                plot,
                "暂无数据",
                self._palette.text_secondary,
                self._palette,
                self._palette.fs(-1, 10),
                align=Qt.AlignCenter,
            )
            return
        slot = plot.width() / n
        bar_w = max(4.0, min(22.0, slot * 0.45))
        points: List[QPoint] = []
        for i, value in enumerate(self._values):
            cx = plot.left() + slot * (i + 0.5)
            h = plot.height() * value / max_value if max_value else 0
            bar = QRectF(cx - bar_w / 2, plot.bottom() - h, bar_w, h)
            grad = QLinearGradient(bar.topLeft(), bar.bottomLeft())
            base = self._palette.accent if i != self._hover else self._palette.accent.lighter(115)
            grad.setColorAt(0, base)
            grad.setColorAt(1, self._palette.alpha(base, 90))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(bar, min(4.0, bar_w / 2), min(4.0, bar_w / 2))
            # 成本折线点（右轴按最大值缩放）
            if i < len(self._costs):
                points.append(QPoint(int(cx), int(plot.bottom() - plot.height() * 0.0)))
            label = self._labels[i] if i < len(self._labels) else ""
            _draw_text(
                painter,
                QRectF(cx - slot / 2, plot.bottom() + 6, slot, 18),
                label,
                self._palette.text_secondary,
                self._palette,
                self._palette.fs(-4, 9),
                align=Qt.AlignCenter,
            )

        if self._costs and len(self._costs) == n:
            max_cost = max(self._costs) or 1.0
            line_points: List[QPoint] = []
            for i, cost in enumerate(self._costs):
                cx = plot.left() + slot * (i + 0.5)
                cy = plot.bottom() - plot.height() * (cost / max_cost) * 0.86
                line_points.append(QPoint(int(cx), int(cy)))
            pen = QPen(self._palette.alpha(QColor("#22d3ee"), 230), 2)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            for i in range(len(line_points) - 1):
                painter.drawLine(line_points[i], line_points[i + 1])
            painter.setBrush(QBrush(QColor("#22d3ee")))
            for p in line_points:
                painter.drawEllipse(p, 2.5, 2.5)

    def _hit(self, x: float) -> int:
        if not self._values:
            return -1
        left, right = self._left_margin(), 12
        width = max(10, self.width() - left - right)
        slot = width / len(self._values)
        idx = int((x - left) // slot)
        return idx if 0 <= idx < len(self._values) else -1

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        idx = self._hit(event.pos().x())
        if idx != self._hover:
            self._hover = idx
            self.update()
        if idx >= 0:
            label = self._labels[idx] if idx < len(self._labels) else ""
            cost = self._costs[idx] if idx < len(self._costs) else 0.0
            show_chart_tooltip(self, event.globalPos(), f"{label}\n{fmt_int(self._values[idx])} tokens\n≈ {fmt_cost(cost)}", self._palette)
        else:
            hide_chart_tooltip()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = -1
        self.update()
        super().leaveEvent(event)


class Heatmap(QWidget):
    """近 N 周日活热力图，点击某天发日期。"""

    dayClicked = pyqtSignal(str)

    _WEEKS = 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self._palette = Palette()
        self._values: Dict[str, int] = {}
        self._cells: List[Tuple[QRectF, str, int]] = []
        self._hover = ""
        self.setMouseTracking(True)
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def set_data(self, values: Dict[str, int]) -> None:
        self._values = {str(k): max(0, int(v)) for k, v in (values or {}).items()}
        self.update()

    def _color_for(self, value: int, max_value: int) -> QColor:
        if value <= 0:
            return self._palette.alpha(self._palette.border, 55)
        ratio = value / max_value if max_value else 0
        alpha = int(50 + 190 * min(1.0, math.sqrt(ratio)))
        return self._palette.alpha(self._palette.accent, alpha)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        from datetime import date, timedelta

        today = date.today()
        # 从本周一往前推 (WEEKS-1) 周
        monday = today - timedelta(days=today.weekday())
        start = monday - timedelta(days=7 * (self._WEEKS - 1))
        left = 30
        top = 18
        available_w = max(10, self.width() - left - 8)
        available_h = max(10, self.height() - top - 8)
        cell_w = max(7.0, min(30.0, available_w / self._WEEKS - 3))
        cell_h = max(8.0, min(20.0, available_h / 7 - 3))
        gap = 3.0
        self._cells = []
        max_value = max(self._values.values() or [0])
        # 星期标签
        for row, label in ((0, "一"), (2, "三"), (4, "五"), (6, "日")):
            _draw_text(
                painter,
                QRectF(0, top + row * (cell_h + gap), left - 6, cell_h),
                label,
                self._palette.text_secondary,
                self._palette,
                self._palette.fs(-5, 9),
                align=Qt.AlignRight | Qt.AlignVCenter,
            )
        last_month = -1
        for col in range(self._WEEKS):
            for row in range(7):
                d = start + timedelta(days=col * 7 + row)
                if d > today:
                    continue
                x = left + col * (cell_w + gap)
                y = top + row * (cell_h + gap)
                rect = QRectF(x, y, cell_w, cell_h)
                value = self._values.get(d.isoformat(), 0)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(self._color_for(value, max_value)))
                painter.drawRoundedRect(rect, 2.5, 2.5)
                if self._hover == d.isoformat():
                    painter.setPen(QPen(self._palette.text_primary, 1.2))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 2.5, 2.5)
                self._cells.append((rect, d.isoformat(), value))
                if d.month != last_month and row == 0:
                    last_month = d.month
                    _draw_text(
                        painter,
                        QRectF(x, 0, cell_w + 18, top - 2),
                        f"{d.month}月",
                        self._palette.text_secondary,
                        self._palette,
                        self._palette.fs(-5, 9),
                    )

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        hit = ""
        for rect, day, value in self._cells:
            if rect.contains(event.pos()):
                hit = day
                if day != self._hover:
                    self._hover = day
                    self.update()
                show_chart_tooltip(self, event.globalPos(), f"{day}\n{fmt_int(value)} tokens" if value else f"{day}\n无活动", self._palette)
                break
        if not hit:
            if self._hover:
                self._hover = ""
                self.update()
            hide_chart_tooltip()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        for rect, day, value in self._cells:
            if rect.contains(event.pos()):
                self.dayClicked.emit(day if value > 0 else "")
                break
        super().mousePressEvent(event)


class TrendChart(QWidget):
    """逐步骤上下文趋势（堆叠柱 / 有符号增量）。"""

    stepClicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._palette = Palette()
        self._steps: List[Dict[str, Any]] = []
        self._keys: List[Tuple[str, QColor]] = []
        self._mode = "total"  # total / delta
        self._hover = -1
        self.setMouseTracking(True)
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def set_data(
        self,
        steps: List[Dict[str, Any]],
        keys: List[Tuple[str, QColor]],
        mode: str = "total",
    ) -> None:
        self._steps = steps
        self._keys = keys
        self._mode = mode if mode in ("total", "delta") else "total"
        self._hover = -1
        min_w = max(360, len(steps) * 7)
        self.setMinimumWidth(min_w)
        self.update()

    def _span(self) -> float:
        if self._mode == "delta":
            max_pos = max((max(0, int(s.get("delta", 0))) for s in self._steps), default=0)
            max_neg = max((max(0, -int(s.get("delta", 0))) for s in self._steps), default=0)
            return max(max_pos, max_neg) or 1
        return max([max(1, int(s.get("input", 0))) for s in self._steps] or [1])

    def _left_margin(self) -> float:
        span = self._span()
        return _axis_left(
            self._palette,
            [fmt_k(span * (3 - i) / 3) for i in range(4)],
            self._palette.fs(-5, 9),
        )

    def _bar_rects(self) -> List[Tuple[QRectF, int]]:
        left, right, top, bottom = self._left_margin(), 12, 14, 24
        plot = QRectF(left, top, max(10, self.width() - left - right), max(10, self.height() - top - bottom))
        n = len(self._steps)
        if n == 0:
            return []
        slot = plot.width() / n
        bar_w = max(2.0, min(14.0, slot * 0.62))
        out: List[Tuple[QRectF, int]] = []
        for i in range(n):
            out.append((QRectF(plot.left() + slot * (i + 0.5) - bar_w / 2, plot.top(), bar_w, plot.height()), i))
        return out

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        left, right, top, bottom = self._left_margin(), 12, 14, 24
        plot = QRectF(left, top, max(10, self.width() - left - right), max(10, self.height() - top - bottom))
        n = len(self._steps)
        if n == 0:
            _draw_text(
                painter,
                plot,
                "暂无请求数据",
                self._palette.text_secondary,
                self._palette,
                self._palette.fs(-1, 10),
                align=Qt.AlignCenter,
            )
            return

        # 数值范围
        span = self._span()

        def y_of(value: float) -> float:
            if self._mode == "delta":
                zero = plot.top() + plot.height() * 0.62
                if value >= 0:
                    return zero - plot.height() * 0.58 * value / span
                return zero + plot.height() * 0.30 * (-value) / span
            return plot.bottom() - plot.height() * value / span

        # 网格
        for i in range(4):
            y = plot.top() + plot.height() * i / 3
            painter.setPen(QPen(self._palette.alpha(self._palette.border, 60), 1, Qt.DashLine))
            painter.drawLine(QPoint(int(plot.left()), int(y)), QPoint(int(plot.right()), int(y)))
            value = span * (3 - i) / 3
            _draw_text(
                painter,
                QRectF(0, y - 8, left - 8, 16),
                fmt_k(value),
                self._palette.text_secondary,
                self._palette,
                self._palette.fs(-5, 9),
                align=Qt.AlignRight | Qt.AlignVCenter,
            )
        if self._mode == "delta":
            zero = plot.top() + plot.height() * 0.62
            painter.setPen(QPen(self._palette.alpha(self._palette.border, 140), 1))
            painter.drawLine(QPoint(int(plot.left()), int(zero)), QPoint(int(plot.right()), int(zero)))

        rects = self._bar_rects()
        for rect, i in rects:
            step = self._steps[i]
            if self._mode == "delta":
                delta = int(step.get("delta", 0))
                value = abs(delta)
                top_y = y_of(max(0, delta) if delta >= 0 else 0)
                bottom_y = y_of(0) if delta >= 0 else y_of(delta)
                bar = QRectF(rect.left(), top_y, rect.width(), max(1.0, bottom_y - top_y))
                color = self._palette.accent if delta >= 0 else QColor("#f87171")
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(self._palette.alpha(color, 200)))
                painter.drawRoundedRect(bar, 1.5, 1.5)
            else:
                comp = step.get("composition") or {}
                total = sum(int(v) for v in comp.values()) or 1
                y = plot.bottom()
                for key, color in self._keys:
                    value = int(comp.get(key, 0))
                    if value <= 0:
                        continue
                    h = plot.height() * value / span
                    bar = QRectF(rect.left(), y - h, rect.width(), h + 0.4)
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QBrush(color))
                    painter.drawRect(bar)
                    y -= h
            # 事件标记
            if step.get("event"):
                marker_y = max(plot.top() + 4, y_of(int(step.get("input", 0))) - 6)
                painter.setBrush(QBrush(QColor("#f97316")))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPoint(int(rect.center().x()), int(marker_y)), 2.4, 2.4)
            if i == self._hover:
                painter.setPen(QPen(self._palette.text_primary, 1))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(rect.adjusted(-1, 0, 1, 0))

        # x 轴标签：最多 8 个
        step_n = len(self._steps)
        stride = max(1, step_n // 8)
        slot = plot.width() / max(1, step_n)
        for i in range(0, step_n, stride):
            cx = plot.left() + slot * (i + 0.5)
            label = f"#{i + 1}"
            _draw_text(
                painter,
                QRectF(cx - slot, plot.bottom() + 4, slot * 2, 18),
                label,
                self._palette.text_secondary,
                self._palette,
                self._palette.fs(-5, 9),
                align=Qt.AlignCenter,
            )

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        hit = -1
        for rect, i in self._bar_rects():
            if rect.adjusted(-2, 0, 2, 0).contains(event.pos()):
                hit = i
                break
        if hit != self._hover:
            self._hover = hit
            self.update()
        if hit >= 0:
            step = self._steps[hit]
            parts = [
                f"Step #{hit + 1} · {step.get('ts', '')}",
                f"上下文 ≈ {fmt_int(step.get('input', 0))} tokens",
                f"输出 {fmt_int(step.get('output', 0))} tokens",
            ]
            delta = int(step.get("delta", 0))
            if delta:
                parts.append(f"变化 {'+' if delta >= 0 else ''}{fmt_int(delta)}")
            show_chart_tooltip(self, event.globalPos(), "\n".join(parts), self._palette)
        else:
            hide_chart_tooltip()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        for rect, i in self._bar_rects():
            if rect.adjusted(-2, 0, 2, 0).contains(event.pos()):
                self.stepClicked.emit(i)
                break
        super().mousePressEvent(event)


class RingProgress(QWidget):
    """占用环：中心显示百分比，副标题显示 used / budget。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._palette = Palette()
        self._percent = 0
        self._title = "0%"
        self._sub = ""
        self.setMinimumSize(92, 92)

    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def set_value(self, percent: int, title: str = "", sub: str = "") -> None:
        self._percent = max(0, min(100, int(percent)))
        self._title = title or f"{self._percent}%"
        self._sub = sub
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        side = min(self.width(), self.height()) - 14
        side = max(30, side)
        rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        thickness = max(6.0, side * 0.11)
        pen = QPen(self._palette.track, thickness)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 0, 360 * 16)
        color = self._palette.accent
        if self._percent >= 85:
            color = QColor("#f87171")
        elif self._percent >= 65:
            color = QColor("#fbbf24")
        pen = QPen(color, thickness)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 90 * 16, -int(360 * 16 * self._percent / 100))
        inner = rect.adjusted(thickness, thickness, -thickness, -thickness)
        _draw_text(
            painter,
            QRectF(inner.x(), inner.center().y() - 14, inner.width(), 24),
            self._title,
            self._palette.text_primary,
            self._palette,
            max(13, int(side * 0.16)),
            bold=True,
            align=Qt.AlignCenter,
        )
        if self._sub:
            _draw_text(
                painter,
                QRectF(inner.x(), inner.center().y() + 8, inner.width(), 16),
                self._sub,
                self._palette.text_secondary,
                self._palette,
                self._palette.fs(-5, 9),
                align=Qt.AlignCenter,
            )
