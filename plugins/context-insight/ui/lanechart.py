# -*- coding: utf-8 -*-
"""团队消息轨迹泳道图 —— QPainter 自绘。

布局对齐 dsh-context 的 pulse 时间线语义：每个成员一条横向泳道，事件按
时间沿 x 轴均匀步进；消息点落在收件人泳道中心线，贝塞尔弧线从发件人
泳道拉过去。左侧标签列固定，右侧轨迹随 QScrollArea 横滚，默认锚到最新。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QPoint, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from .theme import Palette
from .tooltip import hide_chart_tooltip, show_chart_tooltip

LANE_H = 56          # 单泳道高度（乘字号缩放系数）
LANE_PAD_V = 8       # 画布上下留白
PITCH = 34           # 相邻事件横向间距
TRACK_PAD = 16       # 轨迹左右留白
LABEL_W = 150        # 左侧固定标签列宽
POINT_R = 6          # 事件点半径
HIT_R = 10           # 命中半径
ARC_ALPHA = 130      # 弧线常态透明度
DIM_ALPHA = 38       # 筛选时非相关元素的透明度

# 回复状态色（done/warn/error），深浅主题各一套
_STATUS_COLORS = {
    "done": ("#2fb344", "#46c455"),
    "warn": ("#d98324", "#e8a04c"),
    "error": ("#cc4444", "#e05d5d"),
}


def _lane_color(index: int, palette: Palette) -> QColor:
    """按泳道序号轮转色相，从主题 accent 起步。"""
    hue = palette.accent.hue()
    if hue < 0:
        hue = 210
    color = QColor.fromHsv((hue + index * 47) % 360, 150, 230 if palette.is_dark else 200)
    return color


def _initials(name: str) -> str:
    """头像缩写：中文名取前两字，英文取词首字母。"""
    trimmed = (name or "").strip()
    if not trimmed:
        return "?"
    chars = [c for c in trimmed if not c.isspace()]
    if chars and ord(chars[0]) > 0x2E00:
        return "".join(chars[:2])
    words = [w for w in trimmed.split() if w]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return trimmed[:2].upper()


def _status_color(event: Dict[str, Any], palette: Palette) -> QColor:
    if event.get("kind") == "reply":
        success = event.get("success", True)
        key = "done" if success else "error"
        fallback_dark, fallback_light = _STATUS_COLORS[key]
        return QColor(fallback_dark if palette.is_dark else fallback_light)
    status = str(event.get("status") or "")
    if status == "pending":
        return palette.alpha(palette.accent, 255)
    return palette.accent


class TeamLaneLabels(QWidget):
    """左侧固定标签列：泳道头像、名字与筛选点击。"""

    laneClicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._palette = Palette()
        self._lanes: List[Dict[str, Any]] = []
        self._selected = ""
        self._lane_h = LANE_H
        self._pad_v = LANE_PAD_V
        self.setFixedWidth(LABEL_W)

    def set_lane_h(self, lane_h: int, pad_v: int) -> None:
        self._lane_h = lane_h
        self._pad_v = pad_v
        self.updateGeometry()
        self.update()

    def set_data(self, lanes: List[Dict[str, Any]], selected: str) -> None:
        self._lanes = lanes
        self._selected = selected or ""
        self.update()

    def minimumSizeHint(self):  # noqa: N802

        return self.size()

    def sizeHint(self):  # noqa: N802
        from PyQt5.QtCore import QSize

        return QSize(LABEL_W, self._pad_v * 2 + self._lane_h * max(1, len(self._lanes)))

    def _lane_rect(self, index: int) -> QRectF:
        top = self._pad_v + index * self._lane_h
        return QRectF(0, top, self.width(), self._lane_h)

    def paintEvent(self, _event) -> None:  # noqa: N802
        if not self._lanes:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        p = self._palette
        lane_h = self._lane_h
        avatar_d = max(26, int(lane_h * 0.52))
        for i, lane in enumerate(self._lanes):
            rect = self._lane_rect(i)
            center_y = rect.top() + lane_h / 2
            name = str(lane.get("agent_name") or "?")
            selected = self._selected and name == self._selected
            if selected:
                painter.fillRect(rect, p.alpha(p.accent, 26))
            # 头像圆
            avatar_rect = QRectF(8, center_y - avatar_d / 2, avatar_d, avatar_d)
            base = _lane_color(i, p)
            painter.setPen(Qt.NoPen)
            painter.setBrush(p.alpha(base, 220 if lane.get("live") else 120))
            painter.drawEllipse(avatar_rect)
            painter.setPen(QPen(p.card_bg, 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(avatar_rect)
            # 缩写字
            initials = _initials(name)
            fs = max(10, int(avatar_d * 0.36))
            font = painter.font()
            font.setPixelSize(fs)
            font.setBold(bool(lane.get("is_leader")))
            painter.setFont(font)
            if initials:
                text_w = QFontMetrics(font).horizontalAdvance(initials)
                painter.setPen(p.card_bg)
                painter.drawText(
                    QRectF(avatar_rect), Qt.AlignCenter,
                    initials if text_w <= avatar_d - 4 else initials[:1],
                )
            # 名字（超宽省略）
            font.setPixelSize(p.fs(-2))
            font.setBold(bool(lane.get("is_leader")))
            painter.setFont(font)
            name_x = 8 + avatar_d + 8
            fm2 = QFontMetrics(font)
            elided = fm2.elidedText(name, Qt.ElideRight, self.width() - name_x - 8)
            painter.setPen(p.text_primary if selected else p.text_secondary)
            painter.drawText(
                QPoint(name_x, int(center_y + fm2.ascent() / 2 - 1)), elided
            )
            # leader 徽标
            if lane.get("is_leader"):
                font.setPixelSize(p.fs(-4))
                painter.setFont(font)
                painter.setPen(p.alpha(p.accent, 230))
                tag = fm2.elidedText("LEAD", Qt.ElideNone, 40)
                painter.drawText(
                    QPoint(name_x + fm2.horizontalAdvance(elided) + 5,
                           int(center_y + fm2.ascent() / 2 - 1)),
                    tag,
                )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        pos = event.pos()
        for i, lane in enumerate(self._lanes):
            if self._lane_rect(i).contains(QPoint(pos.x(), pos.y())):
                self.laneClicked.emit(str(lane.get("agent_name") or ""))
                return
        super().mousePressEvent(event)

    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        self.update()


class TeamLaneCanvas(QWidget):
    """轨迹画布：泳道背景、事件点与弧线，随横向滚动移动。"""

    eventClicked = pyqtSignal(dict)
    eventHovered = pyqtSignal(object)  # event dict / None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._palette = Palette()
        self._lanes: List[Dict[str, Any]] = []
        self._events: List[Dict[str, Any]] = []
        self._points: List[Tuple[float, float, int]] = []  # (x, y, event index)
        self._hover_index = -1
        self._filter_name = ""
        self._lane_h = LANE_H
        self._pad_v = LANE_PAD_V
        self._content_min_w = 0
        self.setMouseTracking(True)

    # ── 数据与布局 ──
    def set_data(
        self,
        lanes: List[Dict[str, Any]],
        events: List[Dict[str, Any]],
        filter_name: str = "",
    ) -> None:
        self._lanes = lanes
        self._events = events
        self._filter_name = filter_name or ""
        self._hover_index = -1
        self._relayout()
        self.update()

    def set_lane_h(self, lane_h: int, pad_v: int) -> None:
        self._lane_h = lane_h
        self._pad_v = pad_v
        self._relayout()
        self.updateGeometry()
        self.update()

    def _lane_index(self, name: str) -> int:
        for i, lane in enumerate(self._lanes):
            if str(lane.get("agent_name") or "") == name:
                return i
        return -1

    def _lane_center_y(self, index: int) -> float:
        return self._pad_v + index * self._lane_h + self._lane_h / 2

    def _relayout(self) -> None:
        n = len(self._events)
        self._points = []
        for i, event in enumerate(self._events):
            lane_idx = self._lane_index(str(event.get("to") or ""))
            if lane_idx < 0:
                continue
            x = TRACK_PAD + i * PITCH + PITCH / 2
            self._points.append((x, self._lane_center_y(lane_idx), i))
        content_w = TRACK_PAD * 2 + max(0, n - 1) * PITCH if n else TRACK_PAD * 2
        self._content_min_w = content_w
        self.setMinimumWidth(max(0, int(content_w)))

    def preferred_height(self) -> int:
        return self._pad_v * 2 + self._lane_h * max(1, len(self._lanes))

    def sizeHint(self):  # noqa: N802
        from PyQt5.QtCore import QSize

        return QSize(int(self._content_min_w), self.preferred_height())

    # ── 绘制 ──
    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        p = self._palette
        w = self.width()
        lane_h = self._lane_h

        # 泳道背景与中心线
        for i in range(len(self._lanes)):
            top = self._pad_v + i * lane_h
            if i % 2 == 1:
                painter.fillRect(QRectF(0, top, w, lane_h), p.alpha(p.border, 16))
            painter.setPen(QPen(p.alpha(p.border, 46), 1))
            center = top + lane_h / 2
            painter.drawLine(QPoint(0, int(center)), QPoint(w, int(center)))

        if not self._events or not self._points:
            return

        # 弧线（先画线再画点，点压线）
        lane_colors = {i: _lane_color(i, p) for i in range(len(self._lanes))}
        dim = bool(self._filter_name)
        for x, y, eidx in self._points:
            event = self._events[eidx]
            from_idx = self._lane_index(str(event.get("from") or ""))
            if from_idx < 0:
                continue
            y_from = self._lane_center_y(from_idx)
            related = (
                not dim
                or str(event.get("from") or "") == self._filter_name
                or str(event.get("to") or "") == self._filter_name
            )
            hovered = eidx == self._hover_index
            color = QColor(lane_colors.get(from_idx, p.accent))
            color.setAlpha(255 if hovered else (ARC_ALPHA if related else DIM_ALPHA))
            pen = QPen(color, 2.4 if hovered else (1.6 if related else 1.2))
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            k = min(96.0, max(24.0, (y - y_from) * 0.5))
            path = QPainterPath()
            path.moveTo(x, y_from)
            path.cubicTo(x, y_from + k, x, y - k, x, y)
            painter.drawPath(path)

        # 事件点
        for x, y, eidx in self._points:
            event = self._events[eidx]
            related = (
                not dim
                or str(event.get("from") or "") == self._filter_name
                or str(event.get("to") or "") == self._filter_name
            )
            hovered = eidx == self._hover_index
            color = _status_color(event, p)
            if not related:
                color = p.alpha(color, DIM_ALPHA)
            painter.setPen(Qt.NoPen)
            if str(event.get("status") or "") == "pending" and event.get("kind") == "task":
                # pending：空心点
                painter.setPen(QPen(color, 2))
                painter.setBrush(p.alpha(p.card_bg, 220))
                painter.drawEllipse(QRectF(x - POINT_R, y - POINT_R, POINT_R * 2, POINT_R * 2))
                painter.setPen(Qt.NoPen)
            else:
                painter.setBrush(color)
                radius = POINT_R + (2 if hovered else 0)
                painter.drawEllipse(QRectF(x - radius, y - radius, radius * 2, radius * 2))
            if hovered:
                painter.setPen(QPen(p.alpha(p.text_primary, 160), 1))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QRectF(x - POINT_R - 4, y - POINT_R - 4, (POINT_R + 4) * 2, (POINT_R + 4) * 2))

    # ── 交互 ──
    def _hit_event(self, pos: QPoint) -> int:
        for x, y, eidx in self._points:
            if abs(pos.x() - x) <= HIT_R and abs(pos.y() - y) <= HIT_R:
                return eidx
        return -1

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        idx = self._hit_event(event.pos())
        if idx != self._hover_index:
            self._hover_index = idx
            self.eventHovered.emit(self._events[idx] if idx >= 0 else None)
            self.update()
        if idx >= 0:
            event_data = self._events[idx]
            direction = "→"
            text = (
                f"{event_data.get('from')} {direction} {event_data.get('to')}  "
                f"{'回复' if event_data.get('kind') == 'reply' else '任务'}"
                + ("（成功）" if event_data.get("kind") == "reply" and event_data.get("success", True) else "")
                + ("（失败）" if event_data.get("kind") == "reply" and not event_data.get("success", True) else "")
                + ("（待处理）" if event_data.get("kind") == "task" and event_data.get("status") == "pending" else "")
                + "\n"
                + str(event_data.get("subject") or "")[:80]
            )
            show_chart_tooltip(self, event.globalPos(), text, self._palette)
        else:
            hide_chart_tooltip()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hover_index != -1:
            self._hover_index = -1
            self.eventHovered.emit(None)
            self.update()
        hide_chart_tooltip()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        idx = self._hit_event(event.pos())
        if idx >= 0:
            self.eventClicked.emit(self._events[idx])
            return
        super().mousePressEvent(event)

    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        self.update()


class TeamLaneChart(QWidget):
    """泳道图组合：固定标签列 + 横向滚动轨迹画布。"""

    eventClicked = pyqtSignal(dict)
    laneClicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._palette = Palette()
        self._selected = ""
        self._anchored = True
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._labels = TeamLaneLabels(self)
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(False)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        self._canvas = TeamLaneCanvas(self)
        self._scroll.setWidget(self._canvas)
        self._canvas.eventClicked.connect(self.eventClicked.emit)
        self._canvas.eventHovered.connect(self._on_hover)
        self._labels.laneClicked.connect(self._on_lane_clicked)
        self._scroll.horizontalScrollBar().valueChanged.connect(self._on_scrolled)
        # 左标签 + 右画布横排
        from PyQt5.QtWidgets import QHBoxLayout

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._labels)
        row.addWidget(self._scroll, 1)
        layout.addLayout(row)

    # ── 对外接口 ──
    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        self._labels.set_palette_obj(palette)
        self._canvas.set_palette_obj(palette)

    def set_data(
        self,
        lanes: List[Dict[str, Any]],
        events: List[Dict[str, Any]],
        filter_name: str = "",
        scale: float = 1.0,
    ) -> None:
        lane_h = max(40, int(LANE_H * scale))
        pad_v = max(6, int(LANE_PAD_V * scale))
        self._labels.set_lane_h(lane_h, pad_v)
        self._canvas.set_lane_h(lane_h, pad_v)
        height = pad_v * 2 + lane_h * max(1, len(lanes))
        self._labels.setFixedHeight(height)
        self._canvas.setFixedHeight(height)
        self._labels.set_data(lanes, self._selected)
        self._canvas.set_data(lanes, events, filter_name)
        if self._anchored:
            bar = self._scroll.horizontalScrollBar()
            bar.setValue(bar.maximum())

    # ── 内部 ──
    def _on_lane_clicked(self, name: str) -> None:
        self._selected = "" if self._selected == name else name
        self._labels.set_data(self._canvas._lanes, self._selected)
        self._canvas.set_data(self._canvas._lanes, self._canvas._events, self._selected)
        self.laneClicked.emit(self._selected)

    def _on_hover(self, event: Optional[dict]) -> None:
        pass

    def _on_scrolled(self, _value: int) -> None:
        bar = self._scroll.horizontalScrollBar()
        self._anchored = bar.value() >= bar.maximum() - 2
