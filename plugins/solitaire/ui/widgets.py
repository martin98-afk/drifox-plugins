# -*- coding: utf-8 -*-
"""接龙插件自定义 Qt 组件

组件清单：
- CardWidget: 单张牌显示（明牌/暗牌），拖拽/双击事件转发给控制器
- DropZone:   空位占位框（牌堆/废牌/收牌堆/牌桌列）

设计约束：
- 牌面用 QPainter 自绘，不依赖图片资源
- 事件转发：CardWidget 只上报，移动规则判定全部在控制器（solitaire_card）
"""

from typing import Callable, Optional

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .game_logic import Card

CARD_W = 64
CARD_H = 90
RADIUS = 6

SUIT_SYMBOLS = {"spades": "♠", "hearts": "♥", "diamonds": "♦", "clubs": "♣"}
SUIT_COLORS = {
    "spades": "#1A1A1A",
    "clubs": "#1A1A1A",
    "hearts": "#D32F2F",
    "diamonds": "#D32F2F",
}
RANK_LABELS = {1: "A", 11: "J", 12: "Q", 13: "K"}


def rank_label(rank: int) -> str:
    return RANK_LABELS.get(rank, str(rank))


class CardWidget(QWidget):
    """单张牌：明牌或暗牌

    拖拽协议：mousePress/Move/Release/DoubleClick 全部转发给 controller，
    是否可拖、落点合法性由 controller 判定。
    """

    def __init__(self, pile: tuple, idx: int, face_up: bool,
                 controller, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._pile = pile
        self._idx = idx
        self._face_up = face_up
        self._card: Optional[Card] = None
        self._controller = controller
        self._press_pos = None

        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(Qt.OpenHandCursor if face_up else Qt.ArrowCursor)

    # ── 数据 ──

    def set_card(self, card: Card):
        self._card = card
        self.update()

    @property
    def pile(self) -> tuple:
        return self._pile

    @property
    def idx(self) -> int:
        return self._idx

    @property
    def card(self) -> Optional[Card]:
        return self._card

    @property
    def is_face_up(self) -> bool:
        return self._face_up

    # ── 事件转发 ──

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_pos = event.pos()
            self._controller.on_card_pressed(self, event.globalPos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_pos is not None and (event.buttons() & Qt.LeftButton):
            self._controller.on_card_drag_move(self, event.globalPos())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._press_pos is not None:
            self._controller.on_card_release(self, event.globalPos())
        self._press_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._controller.on_card_double_click(self)
        super().mouseDoubleClickEvent(event)

    # ── 绘制 ──

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._face_up and self._card is not None:
            self._paint_face(p)
        else:
            self._paint_back(p)

    def _paint_face(self, p: QPainter):
        card = self._card
        # 白底圆角
        p.setPen(QPen(QColor(0, 0, 0, 40), 1))
        p.setBrush(QColor("#FDFDF8"))
        p.drawRoundedRect(0, 0, CARD_W - 1, CARD_H - 1, RADIUS, RADIUS)

        color = QColor(SUIT_COLORS[card.suit])
        sym = SUIT_SYMBOLS[card.suit]
        p.setPen(color)

        # 左上角 rank + 花色
        p.setFont(QFont("Segoe UI", 10, QFont.Bold))
        p.drawText(QRect(5, 2, 26, 16), Qt.AlignLeft | Qt.AlignTop,
                   rank_label(card.rank))
        p.drawText(QRect(5, 17, 20, 18), Qt.AlignLeft | Qt.AlignTop, sym)

        # 右下角倒置 rank + 花色
        p.save()
        p.translate(CARD_W, CARD_H)
        p.rotate(180)
        p.drawText(QRect(5, 2, 26, 16), Qt.AlignLeft | Qt.AlignTop,
                   rank_label(card.rank))
        p.drawText(QRect(5, 17, 20, 18), Qt.AlignLeft | Qt.AlignTop, sym)
        p.restore()

        # 中央大花色
        p.setFont(QFont("Segoe UI Symbol", 24))
        p.drawText(QRect(0, 0, CARD_W, CARD_H),
                   Qt.AlignCenter, sym)

    def _paint_back(self, p: QPainter):
        # 深蓝底 + 内框线 + 中央淡花色
        p.setPen(QPen(QColor(0, 0, 0, 40), 1))
        p.setBrush(QColor("#2E4A66"))
        p.drawRoundedRect(0, 0, CARD_W - 1, CARD_H - 1, RADIUS, RADIUS)
        p.setPen(QPen(QColor(255, 255, 255, 70), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(4, 4, CARD_W - 9, CARD_H - 9, 4, 4)
        p.setPen(QColor(255, 255, 255, 50))
        p.setFont(QFont("Segoe UI Symbol", 22))
        p.drawText(QRect(0, 0, CARD_W, CARD_H), Qt.AlignCenter, "♠")


class DropZone(QWidget):
    """空位占位框

    kind: "stock"（循环符号）/ "waste" / "foundation"（花色符号）/ "col"
    stock 占位框可点击（重置牌堆）。
    """

    def __init__(self, kind: str, suit: Optional[str] = None,
                 on_click: Optional[Callable[[], None]] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._kind = kind
        self._suit = suit
        self._on_click = on_click
        self.setFixedSize(CARD_W, CARD_H)
        if on_click is not None:
            self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._on_click is not None:
            self._on_click()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # 半透明深色底 + 虚线框（绿桌布上）
        p.setPen(QPen(QColor(255, 255, 255, 60), 1, Qt.DashLine))
        p.setBrush(QColor(0, 0, 0, 45))
        p.drawRoundedRect(0, 0, CARD_W - 1, CARD_H - 1, RADIUS, RADIUS)

        # 中心符号
        if self._kind == "stock":
            sym, alpha, size = "↻", 130, 20
        elif self._kind == "foundation":
            sym, alpha, size = SUIT_SYMBOLS.get(self._suit, ""), 80, 24
        else:
            return
        p.setPen(QColor(255, 255, 255, alpha))
        p.setFont(QFont("Segoe UI Symbol", size))
        p.drawText(QRect(0, 0, CARD_W, CARD_H), Qt.AlignCenter, sym)
