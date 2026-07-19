# -*- coding: utf-8 -*-
"""打砖块插件自定义 Qt 组件

组件清单：
- GameCanvas: 游戏画布（使用 QWidget + QPainter 绘制游戏）
- StatusBar: 状态栏（分数、生命值、开始按钮）
- ControlHint: 操作提示
"""

from PyQt5.QtCore import Qt, QRectF, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


# ── 颜色定义 ──
BRICK_COLORS_QT = [
    QColor("#E94560"),  # 红色
    QColor("#FF7043"),  # 橙色
    QColor("#FFCA28"),  # 黄色
    QColor("#66BB6A"),  # 绿色
    QColor("#42A5F5"),  # 蓝色
]

PADDLE_COLOR = QColor("#42A5F5")
BALL_COLOR = QColor("#FFFFFF")
WALL_COLOR = QColor("#4A5568")


class GameCanvas(QWidget):
    """游戏画布

    使用 QPainter 绘制游戏画面：
    - 砖块矩阵
    - 挡板
    - 小球
    - 边框
    """

    def __init__(self, width: int = 400, height: int = 500, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

        self._width = width
        self._height = height

        # 游戏数据
        self._ball = None
        self._paddle = None
        self._bricks = []
        self._game_state = None

        # 样式
        self._bg_color = QColor("#1A202C")
        self._border_color = QColor("#4A5568")

    def set_game_data(self, state: dict):
        """设置游戏数据（从 BreakoutGame 获取）

        Args:
            state: BreakoutGame.get_state() 返回的字典
        """
        self._game_state = state.get("state")
        self._ball = state.get("ball")
        self._paddle = state.get("paddle")
        self._bricks = state.get("bricks", [])
        self.update()

    def paintEvent(self, event: QPaintEvent):
        """绘制游戏画面"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 背景
        painter.fillRect(self.rect(), self._bg_color)

        # 绘制边框
        painter.setPen(QPen(self._border_color, 2))
        painter.drawRect(0, 0, self._width - 1, self._height - 1)

        # 绘制砖块
        self._draw_bricks(painter)

        # 绘制挡板
        self._draw_paddle(painter)

        # 绘制小球
        self._draw_ball(painter)

        # 绘制游戏状态提示
        self._draw_state_hint(painter)

    def _draw_bricks(self, painter: QPainter):
        """绘制砖块"""
        for brick in self._bricks:
            if not brick.get("alive", True):
                continue

            x = brick.get("x", 0)
            y = brick.get("y", 0)
            w = brick.get("width", 40)
            h = brick.get("height", 20)
            color_str = brick.get("color", "#E94560")

            # 颜色（带点透明度显得更有层次感）
            color = QColor(color_str)
            brush = QBrush(color.lighter(110))
            painter.setBrush(brush)
            painter.setPen(QPen(color.darker(130), 1))

            # 圆角矩形
            rect = QRectF(x + 1, y + 1, w - 2, h - 2)
            painter.drawRoundedRect(rect, 3, 3)

            # 高光效果
            highlight = QBrush(color.lighter(150))
            highlight_rect = QRectF(x + 2, y + 2, w - 4, h // 3)
            painter.fillRect(highlight_rect, highlight)

    def _draw_paddle(self, painter: QPainter):
        """绘制挡板"""
        if not self._paddle:
            return

        x = self._paddle.get("x", 0)
        y = self._paddle.get("y", 0)
        w = self._paddle.get("width", 100)
        h = self._paddle.get("height", 12)

        # 挡板渐变
        gradient_color = QColor("#42A5F5")
        brush = QBrush(gradient_color.lighter(120))
        painter.setBrush(brush)
        painter.setPen(QPen(gradient_color.darker(130), 1))

        rect = QRectF(x, y, w, h)
        painter.drawRoundedRect(rect, 4, 4)

        # 高光
        highlight = QBrush(gradient_color.lighter(160))
        highlight_rect = QRectF(x + 2, y + 2, w - 4, h // 3)
        painter.fillRect(highlight_rect, highlight)

    def _draw_ball(self, painter: QPainter):
        """绘制小球"""
        if not self._ball:
            return

        x = self._ball.get("x", 200)
        y = self._ball.get("y", 300)
        r = self._ball.get("radius", 8)

        # 小球主体
        ball_color = QColor("#FFFFFF")
        brush = QBrush(ball_color)
        painter.setBrush(brush)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(int(x - r), int(y - r), int(r * 2), int(r * 2))

        # 高光
        highlight_color = QColor("#FFFFFF")
        highlight = QBrush(highlight_color.lighter(150))
        painter.setBrush(highlight)
        painter.drawEllipse(int(x - r * 0.6), int(y - r * 0.6),
                           int(r * 0.8), int(r * 0.8))

    def _draw_state_hint(self, painter: QPainter):
        """绘制状态提示文字"""
        if not self._game_state:
            return

        from .game_logic import GameState

        if self._game_state == GameState.READY:
            text = "点击开始"
        elif self._game_state == GameState.WON:
            text = "🎉 胜利！"
        elif self._game_state == GameState.LOST:
            text = "💔 游戏结束"
        else:
            return

        # 绘制半透明背景
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 150)))
        painter.drawRect(0, self._height // 2 - 30, self._width, 60)

        # 绘制文字
        painter.setPen(QPen(QColor("#FFFFFF"), 2))
        font = QFont("Microsoft YaHei", 16, QFont.Bold)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, text)

    def mouseMoveEvent(self, event: QMouseEvent):
        """鼠标移动事件（控制挡板）"""
        # 通知父组件处理
        self.parent().mouse_move_handler(event.x()) if hasattr(self.parent(), 'mouse_move_handler') else None

    def mousePressEvent(self, event: QMouseEvent):
        """鼠标点击事件（发射球/开始游戏）"""
        self.parent().mouse_click_handler() if hasattr(self.parent(), 'mouse_click_handler') else None


class StatusBar(QWidget):
    """状态栏：分数 | 生命值 | 控制按钮"""

    start_clicked = pyqtSignal()
    restart_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(16)

        # 分数显示
        score_layout = QVBoxLayout()
        score_layout.setSpacing(0)

        score_label = QLabel("分数", self)
        score_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.5);
                font-size: 11px;
                background: transparent;
            }
        """)
        score_layout.addWidget(score_label)

        self._score_value = QLabel("0", self)
        self._score_value.setStyleSheet("""
            QLabel {
                color: #FFCA28;
                font-family: 'Courier New', monospace;
                font-size: 22px;
                font-weight: bold;
                background: transparent;
            }
        """)
        score_layout.addWidget(self._score_value)
        layout.addLayout(score_layout)

        layout.addStretch(1)

        # 生命值显示
        lives_layout = QVBoxLayout()
        lives_layout.setSpacing(0)

        lives_label = QLabel("生命", self)
        lives_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.5);
                font-size: 11px;
                background: transparent;
            }
        """)
        lives_layout.addWidget(lives_label)

        self._lives_value = QLabel("❤️❤️❤️", self)
        self._lives_value.setStyleSheet("""
            QLabel {
                font-size: 18px;
                background: transparent;
            }
        """)
        lives_layout.addWidget(self._lives_value)
        layout.addLayout(lives_layout)

        layout.addStretch(1)

        # 控制按钮
        self._start_btn = QPushButton("开始", self)
        self._start_btn.setFixedHeight(32)
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.clicked.connect(self._on_start_clicked)
        self._start_btn.setStyleSheet("""
            QPushButton {
                background: rgba(66, 165, 245, 0.8);
                border: none;
                border-radius: 16px;
                color: white;
                font-size: 13px;
                font-weight: bold;
                padding: 0 20px;
            }
            QPushButton:hover {
                background: rgba(66, 165, 245, 1);
            }
            QPushButton:pressed {
                background: rgba(66, 165, 245, 0.9);
            }
        """)
        layout.addWidget(self._start_btn)

        # 重新开始按钮（默认隐藏）
        self._restart_btn = QPushButton("重新开始", self)
        self._restart_btn.setFixedHeight(32)
        self._restart_btn.setCursor(Qt.PointingHandCursor)
        self._restart_btn.clicked.connect(self.restart_clicked.emit)
        self._restart_btn.hide()
        self._restart_btn.setStyleSheet("""
            QPushButton {
                background: rgba(233, 69, 96, 0.8);
                border: none;
                border-radius: 16px;
                color: white;
                font-size: 13px;
                font-weight: bold;
                padding: 0 16px;
            }
            QPushButton:hover {
                background: rgba(233, 69, 96, 1);
            }
        """)
        layout.addWidget(self._restart_btn)

    def _on_start_clicked(self):
        self.start_clicked.emit()
        # 点击后隐藏开始按钮
        self._start_btn.hide()

    def set_score(self, score: int):
        """更新分数显示"""
        self._score_value.setText(str(score))

    def set_lives(self, lives: int):
        """更新生命值显示"""
        hearts = "❤️" * lives + "🖤" * (3 - lives)
        self._lives_value.setText(hearts)

    def show_start_button(self):
        """显示开始按钮"""
        self._start_btn.show()
        self._restart_btn.hide()

    def show_restart_button(self):
        """显示重新开始按钮"""
        self._start_btn.hide()
        self._restart_btn.show()

    def reset(self):
        """重置状态栏"""
        self.set_score(0)
        self.set_lives(3)
        self.show_start_button()


class ControlHint(QWidget):
    """操作提示组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        hints = [
            ("🖱️", "鼠标控制挡板"),
            ("🎯", "击碎砖块得分"),
            ("❤️", "3条生命"),
        ]

        for icon, text in hints:
            hint_widget = QLabel(f"{icon} {text}", self)
            hint_widget.setStyleSheet("""
                QLabel {
                    color: rgba(255, 255, 255, 0.4);
                    font-size: 11px;
                    background: transparent;
                }
            """)
            layout.addWidget(hint_widget)

        layout.addStretch(1)