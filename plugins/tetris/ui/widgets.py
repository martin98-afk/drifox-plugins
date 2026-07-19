# -*- coding: utf-8 -*-
"""俄罗斯方块插件自定义 Qt 组件

组件清单：
- TetrisBoardCanvas: 棋盘绘制画布（主动刷新，响应键盘）
- PreviewCanvas: 下一块预览画布
- StatusBar: 状态栏（分数/等级/行数）
- ControlHints: 按键提示
"""

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QPainter, QPen, QBrush, QColor, QKeyEvent
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QVBoxLayout, QSizePolicy

from .game_logic import TETROMINOES


# ── 绘制辅助 ──

BLOCK_BORDER_RADIUS = 3
BOARD_LINE_COLOR_LIGHT = "rgba(128,128,128,0.12)"
BOARD_LINE_COLOR_DARK = "rgba(255,255,255,0.08)"


def _draw_block(painter: QPainter, x: int, y: int, size: int, color: str,
                ghost: bool = False):
    """在 (x, y) 位置绘制一个方块格子"""
    pad = 1
    r = BLOCK_BORDER_RADIUS
    rect = painter.window()

    block_w = size - pad * 2
    bx = x * size + pad
    by = y * size + pad

    # 背景 + 边框
    if ghost:
        gc = QColor(color).lighter(150)
        gc.setAlpha(51)  # 20% 透明
        painter.setPen(QPen(QColor(color).lighter(150), 1))
        painter.setBrush(QBrush(gc))
    else:
        # 渐变效果：顶部亮、底部暗
        base = QColor(color)
        top = base.lighter(130)
        bottom = base.darker(115)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(top))
        # 绘制带圆角矩形
        painter.drawRoundedRect(bx, by, block_w, block_w // 2, r, r)
        painter.setBrush(QBrush(bottom))
        painter.drawRoundedRect(bx, by + block_w // 2, block_w, (block_w + 1) // 2, r, r)

        # 内边框高光
        highlight = QColor(255, 255, 255, 60)
        painter.setPen(QPen(highlight, 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(bx + 1, by + 1, block_w - 2, block_w - 2, r - 1, r - 1)


def _is_dark_color(color_str: str) -> bool:
    """判断颜色是否为深色（用于文字）"""
    c = QColor(color_str)
    # 简易亮度判断
    return c.red() * 0.299 + c.green() * 0.587 + c.blue() * 0.114 < 128


# ── 棋盘画布 ──

class TetrisBoardCanvas(QWidget):
    """俄罗斯方块棋盘绘制画布

    特性：
    - 主动 QTimer 驱动重绘（与游戏逻辑 tick 分离）
    - 拦截键盘事件（方向键/空格/P）
    - 支持键盘操作信号
    """

    # 键盘信号
    left_pressed = pyqtSignal()
    right_pressed = pyqtSignal()
    up_pressed = pyqtSignal()     # 旋转
    down_pressed = pyqtSignal()   # 软降
    space_pressed = pyqtSignal()  # 硬降
    pause_pressed = pyqtSignal()  # 暂停

    # 清行动画信号
    clearing_done = pyqtSignal()

    def __init__(self, board_width: int = 10, board_height: int = 20,
                 cell_size: int = 26, parent=None):
        super().__init__(parent)
        self._board_w = board_width
        self._board_h = board_height
        self._cell_size = cell_size

        self.setFixedSize(board_width * cell_size, board_height * cell_size)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()

        # 游戏数据缓存（由 card 注入）
        self._board_data: list = []
        self._current_piece: dict = None
        self._ghost_piece: list = []  # 幽灵方块（落点预览）

        # 跟随主题
        self._line_color = BOARD_LINE_COLOR_LIGHT

        # ★ 清行动画状态
        self._clearing_rows: list = []   # 正在闪烁消除的行号
        self._flash_visible: bool = True  # 闪烁帧标志
        self._flash_count: int = 0        # 已闪烁次数
        self._flash_total: int = 0        # 总闪烁次数
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_interval = 60  # 毫秒

    def set_theme(self, is_dark: bool):
        self._line_color = BOARD_LINE_COLOR_DARK if is_dark else BOARD_LINE_COLOR_LIGHT
        self.update()

    def set_game_data(self, board_data, current_piece, ghost_cells):
        """注入棋盘数据并触发重绘"""
        self._board_data = board_data
        self._current_piece = current_piece
        self._ghost_piece = ghost_cells
        self.update()

    # ★ 清行闪烁动画

    def start_clearing_animation(self, rows: list, flash_count: int = 3):
        """启动消行闪烁效果"""
        self._clearing_rows = list(rows)
        self._flash_visible = True
        self._flash_count = 0
        self._flash_total = flash_count * 2  # 每轮闪烁 x2（亮/灭各一次）
        self._anim_timer.start(self._anim_interval)
        self.update()

    def _on_anim_tick(self):
        """闪烁动画时钟"""
        self._flash_count += 1
        self._flash_visible = not self._flash_visible
        self.update()

        if self._flash_count >= self._flash_total:
            self._anim_timer.stop()
            self._clearing_rows = []
            self.clearing_done.emit()

    def is_animating(self) -> bool:
        """是否正在播放动画"""
        return self._anim_timer.isActive()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 背景
        painter.fillRect(0, 0, self.width(), self.height(), QColor(20, 20, 30))

        # 网格线
        painter.setPen(QPen(QColor(self._line_color), 1))
        for x in range(1, self._board_w):
            painter.drawLine(x * self._cell_size, 0, x * self._cell_size, self.height())
        for y in range(1, self._board_h):
            painter.drawLine(0, y * self._cell_size, self.width(), y * self._cell_size)

        if not self._board_data:
            return

        # 已落方块
        for x in range(self._board_w):
            col = self._board_data[x]
            for y in range(self._board_h):
                if col and y < len(col) and col[y]:
                    # 如果该行正在闪烁消除，用白色方块代替
                    if self._clearing_rows and y in self._clearing_rows:
                        if self._flash_visible:
                            _draw_block(painter, x, y, self._cell_size, "#ffffff")
                        else:
                            _draw_block(painter, x, y, self._cell_size, col[y])
                    else:
                        _draw_block(painter, x, y, self._cell_size, col[y])

        # ★ 闪烁行高亮遮罩（整行白色闪光）
        if self._clearing_rows and self._flash_visible:
            for y in self._clearing_rows:
                painter.fillRect(
                    0, y * self._cell_size,
                    self._board_w * self._cell_size, self._cell_size,
                    QColor(255, 255, 255, 80)
                )

        # 幽灵方块（落点预览，闪烁时隐藏避免干扰）
        if not self._clearing_rows:
            for (x, y) in self._ghost_piece:
                if 0 <= x < self._board_w and 0 <= y < self._board_h:
                    _draw_block(painter, x, y, self._cell_size,
                                self._current_piece["color"] if self._current_piece else "#aaa",
                                ghost=True)

        # 当前活动方块（闪烁时隐藏）
        if self._current_piece and not self._clearing_rows:
            color = TETROMINOES.get(self._current_piece["type"], {}).get("color", "#fff")
            for cx, cy in self._current_piece.get("cells", []):
                if 0 <= cx < self._board_w and 0 <= cy < self._board_h:
                    _draw_block(painter, cx, cy, self._cell_size, color)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key_Left:
            self.left_pressed.emit()
        elif key == Qt.Key_Right:
            self.right_pressed.emit()
        elif key == Qt.Key_Up:
            self.up_pressed.emit()
        elif key == Qt.Key_Down:
            self.down_pressed.emit()
        elif key == Qt.Key_Space:
            self.space_pressed.emit()
        elif key == Qt.Key_P:
            self.pause_pressed.emit()
        else:
            super().keyPressEvent(event)


# ── 下一块预览画布 ──

class PreviewCanvas(QWidget):
    """下一块预览画布"""

    def __init__(self, size: int = 120, parent=None):
        super().__init__(parent)
        self._piece_type: Optional[str] = None
        self._cell_size = size // 5  # 预览格子小一些
        self.setFixedSize(size, size)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def set_next_piece(self, piece_type: str):
        self._piece_type = piece_type
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(0, 0, self.width(), self.height(), QColor(30, 30, 40))

        if not self._piece_type or self._piece_type not in TETROMINOES:
            return

        shapes = TETROMINOES[self._piece_type]["shapes"][0]  # 取原始形态
        color = TETROMINOES[self._piece_type]["color"]

        # 计算 bounding box 并居中
        min_cx = min(cx for cx, cy in shapes)
        max_cx = max(cx for cx, cy in shapes)
        min_cy = min(cy for cx, cy in shapes)
        max_cy = max(cy for cx, cy in shapes)
        bw = max_cx - min_cx + 1
        bh = max_cy - min_cy + 1

        offset_x = (self.width() - bw * self._cell_size) // 2 - min_cx * self._cell_size
        offset_y = (self.height() - bh * self._cell_size) // 2 - min_cy * self._cell_size

        painter.save()
        painter.translate(offset_x, offset_y)
        for cx, cy in shapes:
            bx = cx * self._cell_size + 1
            by = cy * self._cell_size + 1
            bs = self._cell_size - 2
            c = QColor(color)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(c.lighter(130)))
            painter.drawRoundedRect(bx, by, bs, bs // 2, 2, 2)
            painter.setBrush(QBrush(c.darker(115)))
            painter.drawRoundedRect(bx, by + bs // 2, bs, (bs + 1) // 2, 2, 2)
        painter.restore()


# ── 状态栏 ──

class StatusBar(QWidget):
    """状态栏：分数 / 等级 / 已消除行数"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(16)

        def make_label(title: str) -> QLabel:
            lbl = QLabel(f"<b>{title}</b>: <span>0</span>", self)
            lbl.setStyleSheet("""
                QLabel {
                    color: rgba(255,255,255,0.75);
                    font-size: 13px;
                    background: transparent;
                }
                QLabel span {
                    color: #4FC3F7;
                    font-weight: bold;
                    font-family: 'Courier New', monospace;
                }
            """)
            return lbl

        self._score_lbl = make_label("分数")
        self._level_lbl = make_label("等级")
        self._lines_lbl = make_label("消除行")

        layout.addWidget(self._score_lbl)
        layout.addWidget(self._level_lbl)
        layout.addWidget(self._lines_lbl)
        layout.addStretch(1)

    def set_score(self, score: int):
        self._score_lbl.setText(f"<b>分数</b>: <span>{score}</span>")

    def set_level(self, level: int):
        self._level_lbl.setText(f"<b>等级</b>: <span>{level}</span>")

    def set_lines(self, lines: int):
        self._lines_lbl.setText(f"<b>消除行</b>: <span>{lines}</span>")

    def update_all(self, score: int, level: int, lines: int):
        self.set_score(score)
        self.set_level(level)
        self.set_lines(lines)


# ── 按键提示 ──

class ControlHints(QWidget):
    """按键提示条"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(12)

        hints = [
            ("←→", "移动"),
            ("↑", "旋转"),
            ("↓", "软降"),
            ("空格", "硬降"),
            ("P", "暂停"),
        ]
        for key, desc in hints:
            lbl = QLabel(f"<b>{key}</b> {desc}", self)
            lbl.setStyleSheet("""
                QLabel {
                    color: rgba(255,255,255,0.35);
                    font-size: 11px;
                    background: transparent;
                }
            """)
            layout.addWidget(lbl)

        layout.addStretch(1)