# -*- coding: utf-8 -*-
"""中国象棋自定义 Qt 组件

组件清单：
- PieceLabel: 圆形棋子标签（红/黑两色 + 立体阴影 + hover/selected 状态）
- ChessBoardView: 棋盘视图（画横竖线 + 九宫星位 + 河界渐变 + 棋子 + 高亮 + hover + 点击事件）

视觉设计（v0.2 — #5 视觉升级）：
- 棋盘底色从纯米黄 → 木纹三层渐变（外部容器 #chessBoardPanel 提供）
- 棋子：圆角 + radial gradient + QGraphicsDropShadowEffect 立体阴影
- hover：金色边框 + 高光背景（hover 由 ChessBoardView.mouseMoveEvent 跟踪驱动）
- 选中：额外外圈 outline
- 九宫星位：实心小圆点代替空心
- 河界：渐变底 + 加粗深棕字体 + 楷体 fallback
"""

from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, pyqtSignal, QRect, QTimer, QPropertyAnimation, pyqtProperty
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QBrush, QLinearGradient
from PyQt5.QtWidgets import QLabel, QWidget, QGraphicsDropShadowEffect, QGraphicsOpacityEffect

from PyQt5 import QtGui  # noqa: F401  # PyQt5 路径颜色需要

from .game_logic import COLS, ROWS, RED, BLACK, side_of, PIECE_CN, make_move
from .theme import (
    BOARD_WOOD, BOARD_LINE, BOARD_TEXT,
    SELECTED_HIGHLIGHT, LEGAL_HIGHLIGHT, LAST_MOVE_HIGHLIGHT,
    HOVER_EMPTY_DOT,
    BOARD_WOOD_TOP, BOARD_WOOD_MID, BOARD_WOOD_BOTTOM,
    USER_ACCENT, USER_PRIMARY,
    PIECE_RED, PIECE_BLACK,
    LAST_MOVE_FROM_HIGHLIGHT, LAST_MOVE_TO_HIGHLIGHT,
    CAPTURED_PIECE_BG, PATH_ARROW_COLOR,
    get_piece_qss, make_piece_shadow,
)


# ── 棋盘配色（保留兼容旧名）──
BOARD_BG = BOARD_WOOD  # 向后兼容别名
HOVER_HIGHLIGHT = "#d4af37"  # 金色 hover 圈


# ── 棋子标签 ──

class PieceLabel(QLabel):
    """圆形棋子 — 红/黑两色 + 立体阴影 + hover/selected QSS 切换

    鼠标穿透：WA_TransparentForMouseEvents 保持 True（点击穿透到 ChessBoardView），
    hover 由 ChessBoardView.mouseMoveEvent 跟踪，调用 set_hover() 触发 setStyleSheet。
    """

    def __init__(self, piece: str, cell: int, parent=None):
        super().__init__(parent)
        self._piece = piece
        self._cell = cell
        self._hover = False
        self._selected = False
        # 根据初始 piece 计算 _side（红/黑）
        self._side: Optional[str] = None
        if piece and piece != ".":
            if side_of(piece) == RED:
                self._side = "red"
            elif side_of(piece) == BLACK:
                self._side = "black"
        self.setFixedSize(int(cell * 0.86), int(cell * 0.86))
        self.setAlignment(Qt.AlignCenter)
        # 关键：让棋子对鼠标透明，点击事件穿透到 ChessBoardView
        # 否则 QLabel 会拦截 mousePressEvent，棋盘视图收不到点击
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        # 立体阴影（PyQt5 QSS 不支持 box-shadow，用 QGraphicsDropShadowEffect）
        self.setGraphicsEffect(make_piece_shadow())
        # 让 #chessPiece 选择器可命中（否则 theme 的 #chessPiece 规则不生效）
        self.setObjectName("chessPiece")
        self._refresh_style()

    def set_piece(self, piece: str):
        self._piece = piece
        if piece == ".":
            self._side = None
        elif side_of(piece) == RED:
            self._side = "red"
        else:
            self._side = "black"
        self._refresh_style()
        self.setVisible(piece != ".")

    def set_hover(self, on: bool) -> None:
        """外部驱动 hover 状态（由 ChessBoardView mouseMoveEvent 调用）"""
        if self._hover == on:
            return
        self._hover = on
        self._refresh_style()

    def set_selected(self, on: bool) -> None:
        """外部驱动选中状态（由 ChessBoardView set_selected 触发）"""
        if self._selected == on:
            return
        self._selected = on
        self._refresh_style()

    def _refresh_style(self):
        if self._piece == "." or not self._side:
            self.setText("")
            self.setVisible(False)
            return
        text = PIECE_CN.get(self._piece, self._piece)
        font_px = int(self._cell * 0.46)
        self.setText(text)
        try:
            self.setStyleSheet(get_piece_qss(self._side, hover=self._hover, selected=self._selected))
        except Exception:
            # 兜底：失败时保留旧 hardcoded QSS，不让棋子消失
            bg = "#fbf2dc"
            text_color = PIECE_RED if self._side == "red" else PIECE_BLACK
            border_color = text_color
            self.setStyleSheet(
                f"QLabel {{ background: {bg}; border: 2px solid {border_color};"
                f" border-radius: {self.width() // 2}px; color: {text_color};"
                f" font-weight: bold; font-family: 'Microsoft YaHei', '楷体';"
                f" font-size: {font_px}px; }}"
            )


# ── 棋盘视图 ──

class ChessBoardView(QWidget):
    """中国象棋棋盘视图 — 自绘棋盘 + 棋子 + 交互 + hover 跟踪

    视觉升级（#5）：
    - paintEvent 内绘制木纹渐变 + 圆角外框 + 内阴影（替代原 fillRect 实色）
    - 九宫星位改为实心小圆点
    - 河界中央加横线渐变底色 + 加粗深棕字体
    - mouseMoveEvent 跟踪鼠标位置：空格时画淡黄小圆点；棋子时 set_hover(True)
    """

    clicked = pyqtSignal(int, int)  # (col, row)

    def __init__(self, cell: int = 52, parent=None):
        super().__init__(parent)
        # 鼠标跟踪开启（mouseMoveEvent 才会持续触发，无须按住键）
        self.setMouseTracking(True)
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
        # 鼠标当前位置（hover 跟踪）
        self._hover_pos: Optional[Tuple[int, int]] = None
        self._last_hover_piece: Optional[Tuple[int, int]] = None  # 上次 hover 的棋位

        # 动效状态（#6 新增）
        self._board_snapshot: List[List[str]] = []   # 走子前快照（外部注入）
        self._anim_timer: Optional[QTimer] = None
        self._animating: bool = False
        self._anim_from: Optional[Tuple[int, int]] = None
        self._anim_to: Optional[Tuple[int, int]] = None
        self._anim_path: List[Tuple[int, int]] = []
        self._anim_frame: int = 0

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
        # 旧选中位的 PieceLabel 取消 selected
        if self._selected and self._selected in self._pieces:
            self._pieces[self._selected].set_selected(False)
        self._selected = pos
        # 新选中位的 PieceLabel 设 selected
        if pos and pos in self._pieces:
            self._pieces[pos].set_selected(True)
        self.update()

    def set_legal_targets(self, targets: List[Tuple[int, int]]):
        self._legal_targets = list(targets)
        self.update()

    def set_last_move(self, move: Optional[Tuple[int, int, int, int]]):
        self._last_move = move
        self.update()

    # ════════════════════════════════════════════════════════════════
    #  走子动效（#6 升级）
    # ════════════════════════════════════════════════════════════════

    # 脉冲常量
    ANIM_PULSE_FRAMES = 30        # 30 帧 × 50ms = 1.5s
    ANIM_PULSE_INTERVAL = 50      # ms
    ANIM_CAPTURE_FADE_MS = 1000   # 被吃棋子淡出 1s

    # 车（R/r）和炮（C/c）的字符集合
    _LINEAR_PIECE_TYPES = frozenset(["R", "r", "C", "c"])

    def animate_last_move(self, from_pos: Tuple[int, int], to_pos: Tuple[int, int],
                          piece_type: Optional[str] = None,
                          captured_piece: Optional[Tuple[str, int, int]] = None) -> None:
        """启动走子后的视觉动效（起点蓝脉冲 + 终点金脉冲 + 可选路径箭头）。

        Args:
            from_pos: (c, r) 起点
            to_pos:   (c, r) 终点
            piece_type: 移动的棋子字符（'R/r/C/c' 时画路径箭头，其它为 None）
            captured_piece: 被吃棋子 (char, c, r)；None 时不画淡出
        """
        # 旧 timer 清理（避免叠加）
        if self._anim_timer is not None and self._anim_timer.isActive():
            self._anim_timer.stop()

        self._anim_from = from_pos
        self._anim_to = to_pos
        self._anim_frame = 0
        self._animating = True

        # 路径：仅车/炮画虚线箭头
        if piece_type in self._LINEAR_PIECE_TYPES:
            try:
                # 取当前棋盘快照（深拷贝，确保不受主线程修改影响）
                board_snapshot = [row[:] for row in self._board_snapshot]
                path = compute_attack_path(from_pos, to_pos, board_snapshot, piece_type)
            except Exception:
                path = []
            self._anim_path = path
        else:
            self._anim_path = []

        # 启动 QTimer
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(self.ANIM_PULSE_INTERVAL)
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_timer.start()

        # 被吃棋子淡出（QPropertyAnimation）
        if captured_piece is not None:
            self._animate_captured(captured_piece)

        self.update()

    def _on_anim_tick(self) -> None:
        """每 50ms 触发一次：递增帧计数，满 30 帧（1.5s）后停止。"""
        self._anim_frame += 1
        if self._anim_frame >= self.ANIM_PULSE_FRAMES:
            self._stop_animation()
            return
        self.update()

    def _stop_animation(self) -> None:
        """动效结束：清状态 + 停 timer。"""
        self._animating = False
        self._anim_from = None
        self._anim_to = None
        self._anim_path = []
        self._anim_frame = 0
        if self._anim_timer is not None:
            self._anim_timer.stop()
            self._anim_timer = None
        self.update()

    def _animate_captured(self, captured: Tuple[str, int, int]) -> None:
        """在被吃棋子的原位置生成一个淡出副本（QPropertyAnimation 透明度 1.0→0）。

        captured: (piece_char, c, r)
        """
        char, c, r = captured
        if not char or char == ".":
            return

        # 计算屏幕坐标（棋盘格中心）
        piece_size = int(self._cell * 0.86)
        x = self._left + c * self._cell - piece_size // 2
        y = self._top + r * self._cell - piece_size // 2
        if x < 0 or y < 0:
            return

        # 新建淡出副本（与 PieceLabel 同源视觉，但不加入 hover 流）
        ghost = _GhostPieceLabel(char, piece_size, self)
        ghost.move(x, y)
        ghost.set_opacity(1.0)
        ghost.show()

        anim = QPropertyAnimation(ghost, b"opacity", self)
        anim.setDuration(self.ANIM_CAPTURE_FADE_MS)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(ghost.deleteLater)
        anim.start()
        # 防止动画被 GC
        ghost._anim = anim  # type: ignore[attr-defined]

    def set_board_snapshot(self, board) -> None:
        """外部在每次走子前把当前棋盘快照传给 view，用于动效计算路径箭头。"""
        self._board_snapshot = [row[:] for row in board]

    # ── 坐标换算 ──

    def _piece_x(self, c: int) -> int:
        return self._left + c * self._cell - int(self._cell * 0.86) // 2

    def _piece_y(self, r: int) -> int:
        return self._top + r * self._cell - int(self._cell * 0.86) // 2

    def _grid_at(self, mx: int, my: int) -> Optional[Tuple[int, int]]:
        """鼠标坐标 → 格点 (c, r)；越界返回 None"""
        x = mx - self._left
        y = my - self._top
        if x < 0 or y < 0:
            return None
        c = round(x / self._cell)
        r = round(y / self._cell)
        if 0 <= c < COLS and 0 <= r < ROWS:
            return (c, r)
        return None

    # ── 绘制 ──

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        # 背景（木纹三层渐变，圆角矩形）
        self._draw_wood_bg(p)
        # 画棋盘线
        self._draw_lines(p)
        # 九宫（含星位实心圆点）
        self._draw_palaces(p)
        # 河界（渐变底 + 文字）
        self._draw_river(p)
        # 高亮（最后走子 > 选中 > 合法落点 > hover）
        self._draw_highlights(p)
        # 走子动效（#6 新增：脉冲 + 路径箭头；动效期间每帧重绘）
        if self._animating and self._anim_from and self._anim_to:
            self._draw_move_pulse(p)
            self._draw_path_arrow(p)
        p.end()

    def _draw_wood_bg(self, p: QPainter):
        """木纹三层叠加：径向高光 + 重复纹理 + 主渐变。圆角矩形裁剪。"""
        rect = self.rect()
        radius = 8
        # 1) 主底色（线性渐变）
        grad = QLinearGradient(0, 0, 0, rect.height())
        grad.setColorAt(0.0, QColor(BOARD_WOOD_TOP))
        grad.setColorAt(0.5, QColor(BOARD_WOOD_MID))
        grad.setColorAt(1.0, QColor(BOARD_WOOD_BOTTOM))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(rect, radius, radius)

        # 2) 木纹细纹（85度重复线性 + 半透明深褐）
        p.save()
        p.setClipRect(rect)
        p.setPen(QColor(180, 130, 70, 46))  # 18% alpha
        line_step = 6
        stripe_w = 1
        for x in range(rect.left(), rect.right(), line_step):
            p.drawLine(x, rect.top(), x, rect.bottom())
        p.restore()

        # 3) 中心高光（径向）
        p.save()
        p.setClipRect(rect)
        cx = rect.center().x()
        cy = rect.center().y()
        rmax = max(rect.width(), rect.height()) // 2
        from PyQt5.QtGui import QRadialGradient
        rg = QRadialGradient(cx, cy, rmax)
        rg.setColorAt(0.0, QColor(255, 240, 200, 90))   # 35% alpha at center
        rg.setColorAt(0.7, QColor(120, 80, 40, 0))
        rg.setColorAt(1.0, QColor(120, 80, 40, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(rg))
        p.drawRect(rect)
        p.restore()

        # 4) 内阴影：用半透明深棕框边再叠一层
        p.save()
        p.setClipRect(rect)
        pen = QPen(QColor(0, 0, 0, 60))  # rgba(0,0,0,0.24)
        pen.setWidth(6)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect.adjusted(3, 3, -3, -3), radius, radius)
        p.restore()

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
        # 1) "X" 大斜线（保留原行为）
        pen = QPen(QColor(BOARD_LINE))
        pen.setWidth(2)
        p.setPen(pen)
        self._draw_x(p, 3, 5, 0, 2)
        self._draw_x(p, 3, 5, 7, 9)
        # 2) 星位实心小圆点（v0.2 升级：从空心缺口改为实心，#5 设计）
        # 黑方九宫 row 0-2, col 3-5；星位=(c±1, r±1) 在角点
        self._draw_stars(p, 3, 5, 0, 2)
        self._draw_stars(p, 3, 5, 7, 9)

    def _draw_x(self, p: QPainter, c1: int, c2: int, r1: int, r2: int):
        x1 = self._left + c1 * self._cell
        x2 = self._left + c2 * self._cell
        y1 = self._top + r1 * self._cell
        y2 = self._top + r2 * self._cell
        p.drawLine(x1, y1, x2, y2)
        p.drawLine(x1, y2, x2, y1)

    def _draw_stars(self, p: QPainter, c1: int, c2: int, r1: int, r2: int):
        """九宫内 4 个角的星位：小实心圆点（每角 1 个，共 4 角 = 4 点×2 宫 = 8 点）"""
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#3d2817")))  # 深棕
        radius = max(2, int(self._cell * 0.06))
        for cr, cc in [(r1, c1), (r1, c2), (r2, c1), (r2, c2)]:
            x = self._left + cc * self._cell - radius
            y = self._top + cr * self._cell - radius
            p.drawEllipse(x, y, radius * 2, radius * 2)

    def _draw_river(self, p: QPainter):
        """河界（#5 升级）：横向渐变底色 + 加粗深棕字 + 楷体 fallback"""
        # 计算河界区域（row 4 与 row 5 之间）
        y_top = self._top + 4 * self._cell
        y_bot = self._top + 5 * self._cell
        x_left = self._left
        x_right = self._left + (COLS - 1) * self._cell

        # 1) 渐变底色（与棋盘木纹过渡）
        grad = QLinearGradient(x_left, 0, x_right, 0)
        grad.setColorAt(0.0, QColor(BOARD_WOOD_TOP))
        grad.setColorAt(0.5, QColor("#cfa674"))
        grad.setColorAt(1.0, QColor("#a87842"))
        p.fillRect(x_left, y_top, x_right - x_left, y_bot - y_top, QBrush(grad))

        # 2) 中央分隔装饰线（细虚线）
        p.setPen(QPen(QColor(BOARD_LINE), 1, Qt.DashLine))
        y_mid = (y_top + y_bot) // 2
        p.drawLine(x_left + 4, y_mid, x_right - 4, y_mid)

        # 3) 文字（楷体 fallback）
        p.setPen(QColor("#3d2817"))
        font = QFont("STKaiti", int(self._cell * 0.42))
        if not font.exactMatch():
            font = QFont("KaiTi", int(self._cell * 0.42))
            if not font.exactMatch():
                font = QFont("楷体", int(self._cell * 0.42))
        font.setBold(True)
        p.setFont(font)
        rect_left = QRect(
            x_left, y_top,
            4 * self._cell, y_bot - y_top,
        )
        p.drawText(rect_left, Qt.AlignCenter, "楚 河")
        rect_right = QRect(
            x_left + 4 * self._cell, y_top,
            5 * self._cell, y_bot - y_top,
        )
        p.drawText(rect_right, Qt.AlignCenter, "漢 界")

    def _draw_highlights(self, p: QPainter):
        # 最后走子（橘黄点）
        if self._last_move:
            c1, r1, c2, r2 = self._last_move
            self._draw_dot(p, c1, r1, QColor(LAST_MOVE_HIGHLIGHT))
            self._draw_dot(p, c2, r2, QColor(LAST_MOVE_HIGHLIGHT))
        # 选中（金色环）
        if self._selected:
            self._draw_dot(p, self._selected[0], self._selected[1],
                           QColor(SELECTED_HIGHLIGHT), ring=True)
        # 合法落点（绿色实心点）
        for c, r in self._legal_targets:
            self._draw_dot(p, c, r, QColor(LEGAL_HIGHLIGHT))
        # hover：空格显示淡黄小点（已驱动棋子 set_hover 时不画）
        if self._hover_pos is not None:
            c, r = self._hover_pos
            if (c, r) not in self._pieces:
                self._draw_dot(p, c, r, QColor(HOVER_EMPTY_DOT))

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

    # ── 鼠标交互 ──

    def mousePressEvent(self, e):
        pos = self._grid_at(e.x(), e.y())
        if pos is not None:
            self.clicked.emit(pos[0], pos[1])

    def mouseMoveEvent(self, e):
        new_pos = self._grid_at(e.x(), e.y())
        if new_pos == self._hover_pos:
            return  # 状态未变，不重绘
        # 找出新位置的棋子（如有）
        new_piece_pos = new_pos if (new_pos and new_pos in self._pieces) else None
        # 旧棋子取消 hover（无论同位与否）
        if self._last_hover_piece and self._last_hover_piece != new_piece_pos:
            old_lbl = self._pieces.get(self._last_hover_piece)
            if old_lbl is not None:
                old_lbl.set_hover(False)
        # 新棋子设 hover
        if new_piece_pos:
            new_lbl = self._pieces[new_piece_pos]
            new_lbl.set_hover(True)
        self._last_hover_piece = new_piece_pos
        self._hover_pos = new_pos
        self.update()

    def leaveEvent(self, _event):
        # 鼠标离开棋盘：清空 hover
        if self._last_hover_piece:
            old_lbl = self._pieces.get(self._last_hover_piece)
            if old_lbl is not None:
                old_lbl.set_hover(False)
            self._last_hover_piece = None
        if self._hover_pos is not None:
            self._hover_pos = None
            self.update()

    # ── 走子动效绘制（#6 新增） ──

    def _draw_move_pulse(self, p: QPainter) -> None:
        """画走子动效：起点蓝脉冲 + 终点金脉冲（基于帧号计算 alpha）。

        30 帧 = 1.5s。每帧 alpha 走 0→max→0 的半周期。
        """
        frame = self._anim_frame
        max_frame = self.ANIM_PULSE_FRAMES
        # 正弦半周期：alpha(t) = max * sin(π * t / max_frame)
        import math
        progress = frame / max(1, max_frame)
        half = math.sin(math.pi * progress)
        from_alpha = int(180 * half)
        to_alpha = int(220 * half)
        # 颜色：拆解 LAST_MOVE_FROM_HIGHLIGHT = rgba(102,152,255, 0.7)
        p.save()
        p.setPen(Qt.NoPen)

        # 起点：蓝色脉冲矩形
        c, r = self._anim_from
        x0 = self._left + c * self._cell - self._cell // 2
        y0 = self._top + r * self._cell - self._cell // 2
        size = self._cell
        color_from = QColor(102, 152, 255, max(0, min(255, from_alpha)))
        p.setBrush(QBrush(color_from))
        p.drawRoundedRect(x0 + 4, y0 + 4, size - 8, size - 8, 6, 6)

        # 终点：金色脉冲矩形
        c, r = self._anim_to
        x0 = self._left + c * self._cell - self._cell // 2
        y0 = self._top + r * self._cell - self._cell // 2
        color_to = QColor(212, 175, 55, max(0, min(255, to_alpha)))
        p.setBrush(QBrush(color_to))
        p.drawRoundedRect(x0 + 4, y0 + 4, size - 8, size - 8, 6, 6)
        p.restore()

    def _draw_path_arrow(self, p: QPainter) -> None:
        """车/炮移动时画路径虚线箭头。"""
        if not self._anim_path:
            return
        p.save()
        from .theme import PATH_ARROW_COLOR

        pen = QPen(QColor(PATH_ARROW_COLOR))
        pen.setWidth(3)
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        # 画连接相邻格的虚线段
        from PyQt5.QtCore import QPointF

        prev = None
        for c, r in self._anim_path:
            cx = self._left + c * self._cell
            cy = self._top + r * self._cell
            pt = QPointF(cx, cy)
            if prev is not None:
                p.drawLine(prev, pt)
            prev = pt

        # 箭头头：在终点的方向延伸一个三角
        if len(self._anim_path) >= 2:
            c, r = self._anim_to
            tx = self._left + c * self._cell
            ty = self._top + r * self._cell
            # 方向：从倒数第二个格 → 终点
            c2, r2 = self._anim_path[-1]
            dx = tx - (self._left + c2 * self._cell)
            dy = ty - (self._top + r2 * self._cell)
            norm = (dx * dx + dy * dy) ** 0.5
            if norm == 0:
                p.restore()
                return
            ux, uy = dx / norm, dy / norm
            # 三角形顶点：终点 + 两个垂直偏点
            size = 10.0
            # 垂直向量
            vx, vy = -uy, ux
            p1 = QPointF(tx, ty)
            p2 = QPointF(tx - ux * size + vx * size * 0.6,
                         ty - uy * size + vy * size * 0.6)
            p3 = QPointF(tx - ux * size - vx * size * 0.6,
                         ty - uy * size - vy * size * 0.6)
            from PyQt5.QtGui import QPolygonF
            polygon = QPolygonF([p1, p2, p3])
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(PATH_ARROW_COLOR)))
            p.drawPolygon(polygon)
        p.restore()


# ════════════════════════════════════════════════════════════════
#  路径计算（#6 新增）
# ════════════════════════════════════════════════════════════════

def compute_attack_path(from_pos: Tuple[int, int], to_pos: Tuple[int, int],
                        board: List[List[str]], piece_type: str) -> List[Tuple[int, int]]:
    """计算车/炮从 from_pos 直线移动到 to_pos 时穿过的中间格列表（不含起终点）。

    仅处理直线移动（横/竖）。如果 from→to 不共线 → 返回空列表。

    Args:
        from_pos: (c, r) 起点
        to_pos:   (c, r) 终点
        board:    当前棋盘快照（用于炮跳棋架）
        piece_type: 'R/r'（车） / 'C/c'（炮）

    Returns:
        从起点到终点（不含起终点）的中转格列表。
        例如 (0,9) → (0,0) → 返回 [(0,8), (0,7), ..., (0,1)]

    炮的特殊逻辑：返回「从棋架跳过去」之后到达目标前的所有格。
    """
    fc, fr = from_pos
    tc, tr = to_pos
    path: List[Tuple[int, int]] = []

    if fc == tc:
        # 纵向
        step = 1 if tr > fr else -1
        for r in range(fr + step, tr, step):
            path.append((fc, r))
    elif fr == tr:
        # 横向
        step = 1 if tc > fc else -1
        for c in range(fc + step, tc, step):
            path.append((c, fr))
    else:
        # 不共线，非车/炮直线移动
        return []

    # 炮需要跳棋架（去掉棋架之前的格）
    if piece_type in ("C", "c"):
        screen_idx = None  # 路径上第一个非空格（棋架）的下标
        for idx, (c, r) in enumerate(path):
            if board[r][c] != ".":
                screen_idx = idx
                break
        if screen_idx is not None and screen_idx + 1 < len(path):
            return path[screen_idx + 1:]
        # 没找到棋架（=炮不能这样走）或路径太短 → 不画箭头
        return []
    return path


# ════════════════════════════════════════════════════════════════
#  被吃棋子淡出副本（#6 新增）
# ════════════════════════════════════════════════════════════════

class _GhostPieceLabel(QLabel):
    """被吃棋子的淡出副本：保留视觉但不参与交互。

    QPropertyAnimation 调整 windowOpacity 实现淡出。
    """
    def __init__(self, char: str, size: int, parent: QWidget) -> None:
        super().__init__(parent)
        if char == "." or not char:
            return
        from .game_logic import side_of, RED, BLACK, PIECE_CN
        side = side_of(char)
        self._side = "red" if side == RED else ("black" if side == BLACK else None)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.setText(PIECE_CN.get(char, char))
        try:
            from .theme import get_piece_qss
            if self._side:
                self.setStyleSheet(get_piece_qss(self._side))
        except Exception:
            self.setStyleSheet(
                "QLabel { background: #fbf2dc; border: 2px solid #888;"
                "border-radius: 50%; color: #333; font-weight: bold;"
                "font-family: 'Microsoft YaHei', '楷体'; font-size: 22px; }"
            )
        # 淡出副本用 QGraphicsOpacityEffect（setWindowOpacity 仅对顶层窗口有效）
        self._ghost_effect = QGraphicsOpacityEffect(self)
        self._ghost_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._ghost_effect)

    # QPropertyAnimation 需要的 opacity 属性（基于 QGraphicsOpacityEffect）
    def _get_opacity(self) -> float:
        return self._ghost_effect.opacity()

    def _set_opacity(self, v: float) -> None:
        self._ghost_effect.setOpacity(v)

    opacity = pyqtProperty(float, fget=_get_opacity, fset=_set_opacity)
    # 普通方法别名（方便外部 set_opacity(0.5) 调用）
    set_opacity = _set_opacity
    get_opacity = _get_opacity


# ── 向后兼容：导出色值常量给测试 / 旧调用者 ──
__all__ = [
    "BOARD_BG", "BOARD_LINE", "BOARD_TEXT",
    "SELECTED_HIGHLIGHT", "LEGAL_HIGHLIGHT", "LAST_MOVE_HIGHLIGHT",
    "HOVER_HIGHLIGHT",
    "PieceLabel", "ChessBoardView",
    "compute_attack_path",
    "_GhostPieceLabel",
]
