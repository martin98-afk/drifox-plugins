# -*- coding: utf-8 -*-
"""中国象棋自定义 Qt 组件

组件清单：
- PieceLabel: 圆形棋子标签（红/黑两色，中文棋子名）
- ChessBoardView: 棋盘视图（画横竖线 + 九宫 + 河界 + 棋子 + 高亮 + 点击事件）
"""

from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, pyqtSignal, QRect
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QBrush
from PyQt5.QtWidgets import QLabel, QWidget

from .game_logic import COLS, ROWS, RED, BLACK, side_of, PIECE_CN


# ── 棋盘配色 ──
BOARD_BG = "#e8c98a"      # 棋盘米黄
BOARD_LINE = "#3a2a14"    # 棋盘线条（深褐）
BOARD_TEXT = "#3a2a14"    # 河界文字色
SELECTED_HIGHLIGHT = "#f7c948"
LEGAL_HIGHLIGHT = "#88c97a"
LAST_MOVE_HIGHLIGHT = "#d4a93a"


# ── 棋子标签 ──

class PieceLabel(QLabel):
    """圆形棋子 — 红方白底红字，黑方白底黑字"""

    def __init__(self, piece: str, cell: int, parent=None):
        super().__init__(parent)
        self._piece = piece
        self._cell = cell
        self.setFixedSize(int(cell * 0.86), int(cell * 0.86))
        self.setAlignment(Qt.AlignCenter)
        # 关键：让棋子对鼠标透明，点击事件穿透到 ChessBoardView
        # 否则 QLabel 会拦截 mousePressEvent，棋盘视图收不到点击
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._refresh_style()

    def set_piece(self, piece: str):
        self._piece = piece
        self._refresh_style()
        self.setVisible(piece != ".")

    def _refresh_style(self):
        if self._piece == ".":
            self.setText("")
            self.setVisible(False)
            return
        is_red = side_of(self._piece) == RED
        text_color = "#c62828" if is_red else "#1a1a1a"
        border_color = "#c62828" if is_red else "#1a1a1a"
        bg = "#fbf2dc"  # 米白底
        text = PIECE_CN.get(self._piece, self._piece)
        font_px = int(self._cell * 0.46)
        self.setText(text)
        self.setStyleSheet(
            f"QLabel {{"
            f"background: {bg};"
            f"border: 2px solid {border_color};"
            f"border-radius: {self.width() // 2}px;"
            f"color: {text_color};"
            f"font-weight: bold;"
            f"font-family: 'Microsoft YaHei', '楷体';"
            f"font-size: {font_px}px;"
            f"}}"
        )


# ── 棋盘视图 ──

class ChessBoardView(QWidget):
    """中国象棋棋盘视图 — 自绘棋盘 + 棋子 + 交互"""

    clicked = pyqtSignal(int, int)  # (col, row)

    def __init__(self, cell: int = 52, parent=None):
        super().__init__(parent)
        self._cell = cell
        pad = max(18, int(cell * 0.55))
        self._left = pad
        self._top = pad
        self._right = pad
        self._bottom = pad
        self.setFixedSize(
            self._left + (COLS - 1) * self._cell + self._right,
            self._top + (ROWS - 1) * self._cell + self._bottom,
        )
        # 棋子：{(c,r): PieceLabel}
        self._pieces: Dict[Tuple[int, int], PieceLabel] = {}
        # 高亮状态
        self._selected: Optional[Tuple[int, int]] = None
        self._legal_targets: List[Tuple[int, int]] = []
        self._last_move: Optional[Tuple[int, int, int, int]] = None

    # ── 公开接口 ──

    def set_pieces(self, board):
        """按棋盘字符串二维数组设置棋子（'.' 表示空）"""
        # 清除不在新局面的棋子
        to_remove = []
        for pos, lbl in self._pieces.items():
            c, r = pos
            piece = board[r][c]
            if piece == ".":
                lbl.hide()
                to_remove.append(pos)
            else:
                lbl.set_piece(piece)
                lbl.show()
        for pos in to_remove:
            del self._pieces[pos]
        # 新增
        for r in range(ROWS):
            for c in range(COLS):
                piece = board[r][c]
                if piece == ".":
                    continue
                if (c, r) in self._pieces:
                    continue
                lbl = PieceLabel(piece, self._cell, self)
                lbl.move(self._piece_x(c), self._piece_y(r))
                lbl.show()
                self._pieces[(c, r)] = lbl

    def set_selected(self, pos: Optional[Tuple[int, int]]):
        self._selected = pos
        self.update()

    def set_legal_targets(self, targets: List[Tuple[int, int]]):
        self._legal_targets = list(targets)
        self.update()

    def set_last_move(self, move: Optional[Tuple[int, int, int, int]]):
        self._last_move = move
        self.update()

    # ── 坐标换算 ──

    def _piece_x(self, c: int) -> int:
        return self._left + c * self._cell - int(self._cell * 0.86) // 2

    def _piece_y(self, r: int) -> int:
        return self._top + r * self._cell - int(self._cell * 0.86) // 2

    # ── 绘制 ──

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        # 背景（圆角矩形）
        p.fillRect(self.rect(), QColor(BOARD_BG))
        # 画棋盘线
        self._draw_lines(p)
        # 画九宫
        self._draw_palaces(p)
        # 画河界文字
        self._draw_river(p)
        # 高亮（最后走子 > 选中 > 合法落点）
        self._draw_highlights(p)
        p.end()

    def _draw_lines(self, p: QPainter):
        pen = QPen(QColor(BOARD_LINE))
        pen.setWidth(2)
        p.setPen(pen)
        # 9 条竖线（col 0..8），全部贯穿
        for c in range(COLS):
            x = self._left + c * self._cell
            p.drawLine(x, self._top, x, self._top + (ROWS - 1) * self._cell)
        # 10 条横线（row 0..9），全部贯穿
        for r in range(ROWS):
            y = self._top + r * self._cell
            p.drawLine(self._left, y, self._left + (COLS - 1) * self._cell, y)

    def _draw_palaces(self, p: QPainter):
        pen = QPen(QColor(BOARD_LINE))
        pen.setWidth(2)
        p.setPen(pen)
        # 黑方九宫 row 0-2, col 3-5
        self._draw_x(p, 3, 5, 0, 2)
        # 红方九宫 row 7-9, col 3-5
        self._draw_x(p, 3, 5, 7, 9)

    def _draw_x(self, p: QPainter, c1: int, c2: int, r1: int, r2: int):
        x1 = self._left + c1 * self._cell
        x2 = self._left + c2 * self._cell
        y1 = self._top + r1 * self._cell
        y2 = self._top + r2 * self._cell
        p.drawLine(x1, y1, x2, y2)
        p.drawLine(x1, y2, x2, y1)

    def _draw_river(self, p: QPainter):
        # 河界：row 4 和 row 5 之间（横线之间留空隙）。文字写在中线。
        # 在河界居中写"楚河"和"漢界"
        p.setPen(QColor(BOARD_TEXT))
        font = QFont("Microsoft YaHei", int(self._cell * 0.38))
        font.setBold(True)
        p.setFont(font)
        y_mid = self._top + 4 * self._cell + self._cell // 2
        # "楚河"在左半
        rect_left = QRect(
            self._left, y_mid - self._cell // 2,
            4 * self._cell, self._cell
        )
        p.drawText(rect_left, Qt.AlignCenter, "楚 河")
        # "漢界"在右半
        rect_right = QRect(
            self._left + 4 * self._cell, y_mid - self._cell // 2,
            5 * self._cell, self._cell
        )
        p.drawText(rect_right, Qt.AlignCenter, "漢 界")

    def _draw_highlights(self, p: QPainter):
        # 最后走子
        if self._last_move:
            c1, r1, c2, r2 = self._last_move
            self._draw_dot(p, c1, r1, QColor(LAST_MOVE_HIGHLIGHT))
            self._draw_dot(p, c2, r2, QColor(LAST_MOVE_HIGHLIGHT))
        # 选中
        if self._selected:
            self._draw_dot(p, self._selected[0], self._selected[1],
                           QColor(SELECTED_HIGHLIGHT), ring=True)
        # 合法落点（小绿点/绿框）
        for c, r in self._legal_targets:
            self._draw_dot(p, c, r, QColor(LEGAL_HIGHLIGHT))

    def _draw_dot(self, p: QPainter, c: int, r: int,
                  color: QColor, ring: bool = False):
        x = self._left + c * self._cell
        y = self._top + r * self._cell
        radius = int(self._cell * 0.16)
        if ring:
            pen = QPen(color)
            pen.setWidth(3)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(x - radius - 4, y - radius - 4,
                          (radius + 4) * 2, (radius + 4) * 2)
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(color))
            p.drawEllipse(x - radius, y - radius, radius * 2, radius * 2)

    # ── 交互 ──

    def mousePressEvent(self, e):
        x = e.x() - self._left
        y = e.y() - self._top
        if x < 0 or y < 0:
            return
        c = round(x / self._cell)
        r = round(y / self._cell)
        if 0 <= c < COLS and 0 <= r < ROWS:
            self.clicked.emit(c, r)
