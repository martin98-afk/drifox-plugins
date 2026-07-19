# -*- coding: utf-8 -*-
"""贪吃蛇插件自定义 Qt 组件

组件清单：
- GameCanvas: 游戏画布（绘制网格、蛇身、食物）
- StatusBar: 状态栏（分数、速度、暂停按钮）
"""

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QColor, QKeyEvent
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QSizePolicy


# ── 颜色配置 ──
class Colors:
    """颜色配置"""
    # 蛇身颜色
    SNAKE_HEAD = QColor("#4CAF50")
    SNAKE_BODY = QColor("#81C784")
    SNAKE_BORDER = QColor("#2E7D32")

    # 食物颜色
    FOOD = QColor("#E94560")
    FOOD_BORDER = QColor("#C62828")

    # 网格颜色
    GRID_LINE = QColor(128, 128, 128, 40)

    # 背景色
    BACKGROUND = QColor(30, 30, 30)
    GRID_CELL_BG = QColor(45, 45, 45)

    # 文字颜色
    TEXT_PRIMARY = QColor(255, 255, 255, 230)
    TEXT_SECONDARY = QColor(255, 255, 255, 140)


class GameCanvas(QWidget):
    """贪吃蛇游戏画布

    功能：
    - 绘制游戏网格
    - 绘制蛇身（头和身体）
    - 绘制食物
    - 键盘事件处理
    """

    key_pressed = pyqtSignal(int)

    def __init__(self, width: int = 15, height: int = 15, cell_size: int = 28, parent=None):
        super().__init__(parent)
        self._grid_width = width
        self._grid_height = height
        self._cell_size = cell_size

        # 蛇身和食物数据
        self._snake: list = []
        self._food: tuple = (-1, -1)

        # 尺寸计算
        self._canvas_width = width * cell_size
        self._canvas_height = height * cell_size

        self.setFixedSize(self._canvas_width, self._canvas_height)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()

        # 主题色（可动态更新）
        self._theme_colors = {
            "background": Colors.BACKGROUND,
            "grid_cell": Colors.GRID_CELL_BG,
            "grid_line": Colors.GRID_LINE,
            "snake_head": Colors.SNAKE_HEAD,
            "snake_body": Colors.SNAKE_BODY,
            "snake_border": Colors.SNAKE_BORDER,
            "food": Colors.FOOD,
            "food_border": Colors.FOOD_BORDER,
        }

    def set_game_data(self, snake: list, food: tuple):
        """设置游戏数据并重绘

        Args:
            snake: 蛇身坐标列表 [(x, y), ...]
            food: 食物坐标 (x, y)
        """
        self._snake = snake
        self._food = food
        self.update()

    def set_cell_size(self, size: int):
        """更新单元格大小"""
        self._cell_size = size
        self._canvas_width = self._grid_width * size
        self._canvas_height = self._grid_height * size
        self.setFixedSize(self._canvas_width, self._canvas_height)
        self.update()

    def update_theme(self, is_dark: bool):
        """更新主题色"""
        if is_dark:
            self._theme_colors["background"] = QColor(30, 30, 30)
            self._theme_colors["grid_cell"] = QColor(45, 45, 45)
            self._theme_colors["grid_line"] = QColor(128, 128, 128, 40)
        else:
            self._theme_colors["background"] = QColor(240, 240, 240)
            self._theme_colors["grid_cell"] = QColor(255, 255, 255)
            self._theme_colors["grid_line"] = QColor(0, 0, 0, 30)
        self.update()

    def paintEvent(self, event):
        """绘制游戏画面"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 填充背景
        painter.fillRect(0, 0, self._canvas_width, self._canvas_height,
                         self._theme_colors["background"])

        # 绘制网格
        self._draw_grid(painter)

        # 绘制食物
        self._draw_food(painter)

        # 绘制蛇身
        self._draw_snake(painter)

    def _draw_grid(self, painter: QPainter):
        """绘制网格"""
        painter.setPen(self._theme_colors["grid_line"])

        # 垂直线
        for x in range(self._grid_width + 1):
            painter.drawLine(
                x * self._cell_size, 0,
                x * self._cell_size, self._canvas_height
            )

        # 水平线
        for y in range(self._grid_height + 1):
            painter.drawLine(
                0, y * self._cell_size,
                self._canvas_width, y * self._cell_size
            )

    def _draw_food(self, painter: QPainter):
        """绘制食物"""
        if self._food[0] < 0 or self._food[1] < 0:
            return

        x, y = self._food
        padding = 2
        rect = self._get_cell_rect(x, y, padding)

        # 食物主体
        painter.fillRect(rect, self._theme_colors["food"])

        # 食物边框/高光
        pen = QPen(self._theme_colors["food_border"], 1)
        painter.setPen(pen)
        painter.drawEllipse(rect.adjusted(2, 2, -2, -2))

    def _draw_snake(self, painter: QPainter):
        """绘制蛇身"""
        if not self._snake:
            return

        for i, (x, y) in enumerate(self._snake):
            is_head = (i == 0)
            padding = 1 if is_head else 2
            rect = self._get_cell_rect(x, y, padding)

            # 选择颜色
            if is_head:
                color = self._theme_colors["snake_head"]
                border = self._theme_colors["snake_border"]
            else:
                # 身体渐变效果
                color = self._theme_colors["snake_body"]
                border = self._theme_colors["snake_border"]

            painter.fillRect(rect, color)

            # 边框
            pen = QPen(border, 1)
            painter.setPen(pen)
            painter.drawRect(rect)

            # 蛇头眼睛
            if is_head:
                self._draw_eyes(painter, x, y)

    def _draw_eyes(self, painter: QPainter, x: int, y: int):
        """绘制蛇头眼睛"""
        eye_size = max(2, self._cell_size // 8)
        center_x = x * self._cell_size + self._cell_size // 2
        center_y = y * self._cell_size + self._cell_size // 2

        # 眼睛位置（简化为两个点）
        offset = self._cell_size // 4
        eye1 = (center_x - offset, center_y - offset // 2)
        eye2 = (center_x + offset - eye_size, center_y - offset // 2)

        painter.fillRect(int(eye1[0]), int(eye1[1]), eye_size, eye_size, QColor("#fff"))
        painter.fillRect(int(eye2[0]), int(eye2[1]), eye_size, eye_size, QColor("#fff"))

    def _get_cell_rect(self, x: int, y: int, padding: int = 0) -> QColor:
        """获取格子的绘制矩形"""
        from PyQt5.QtCore import QRect
        return QRect(
            x * self._cell_size + padding,
            y * self._cell_size + padding,
            self._cell_size - padding * 2,
            self._cell_size - padding * 2
        )

    def keyPressEvent(self, event: QKeyEvent):
        """处理键盘事件"""
        self.key_pressed.emit(event.key())
        super().keyPressEvent(event)

    def focusInEvent(self, event):
        """获得焦点时重绘"""
        super().focusInEvent(event)
        self.update()


class StatusBar(QWidget):
    """状态栏：分数 | 速度 | 暂停按钮"""

    pause_clicked = pyqtSignal()
    restart_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_paused = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(16)

        # 分数标签
        self._score_label = QLabel("分数: 0", self)
        self._score_label.setStyleSheet("""
            QLabel {
                color: #4FC3F7;
                background: rgba(0, 0, 0, 0.4);
                padding: 4px 12px;
                border-radius: 12px;
                font-family: 'Microsoft YaHei', sans-serif;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        layout.addWidget(self._score_label)

        layout.addStretch(1)

        # 速度标签
        self._speed_label = QLabel("速度: 1x", self)
        self._speed_label.setStyleSheet("""
            QLabel {
                color: #81C784;
                background: rgba(0, 0, 0, 0.4);
                padding: 4px 12px;
                border-radius: 12px;
                font-family: 'Microsoft YaHei', sans-serif;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        layout.addWidget(self._speed_label)

        layout.addStretch(1)

        # 暂停按钮
        self._pause_btn = QPushButton("⏸ 暂停", self)
        self._pause_btn.setFixedHeight(32)
        self._pause_btn.setCursor(Qt.PointingHandCursor)
        self._pause_btn.clicked.connect(self._on_pause_clicked)
        self._pause_btn.setStyleSheet("""
            QPushButton {
                background: rgba(79, 195, 247, 0.2);
                border: 1px solid rgba(79, 195, 247, 0.4);
                border-radius: 16px;
                padding: 4px 16px;
                color: #4FC3F7;
                font-family: 'Microsoft YaHei', sans-serif;
                font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(79, 195, 247, 0.3);
            }
        """)
        layout.addWidget(self._pause_btn)

        # 重新开始按钮
        self._restart_btn = QPushButton("🔄 重开", self)
        self._restart_btn.setFixedHeight(32)
        self._restart_btn.setCursor(Qt.PointingHandCursor)
        self._restart_btn.clicked.connect(self.restart_clicked.emit)
        self._restart_btn.setStyleSheet("""
            QPushButton {
                background: rgba(129, 199, 132, 0.2);
                border: 1px solid rgba(129, 199, 132, 0.4);
                border-radius: 16px;
                padding: 4px 16px;
                color: #81C784;
                font-family: 'Microsoft YaHei', sans-serif;
                font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(129, 199, 132, 0.3);
            }
        """)
        layout.addWidget(self._restart_btn)

    def _on_pause_clicked(self):
        self._is_paused = not self._is_paused
        if self._is_paused:
            self._pause_btn.setText("▶ 继续")
            self._pause_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(233, 69, 96, 0.2);
                    border: 1px solid rgba(233, 69, 96, 0.4);
                    border-radius: 16px;
                    padding: 4px 16px;
                    color: #E94560;
                    font-family: 'Microsoft YaHei', sans-serif;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background: rgba(233, 69, 96, 0.3);
                }
            """)
        else:
            self._pause_btn.setText("⏸ 暂停")
            self._pause_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(79, 195, 247, 0.2);
                    border: 1px solid rgba(79, 195, 247, 0.4);
                    border-radius: 16px;
                    padding: 4px 16px;
                    color: #4FC3F7;
                    font-family: 'Microsoft YaHei', sans-serif;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background: rgba(79, 195, 247, 0.3);
                }
            """)
        self.pause_clicked.emit()

    def set_score(self, score: int):
        """更新分数显示"""
        self._score_label.setText(f"分数: {score}")

    def set_speed(self, interval: int):
        """更新速度显示（基于间隔计算速度倍率）"""
        # 间隔越小，速度越快
        # BASE_INTERVAL = 200, MIN_INTERVAL = 50
        speed = max(1, round((200 - interval) / 15) + 1)
        self._speed_label.setText(f"速度: {speed}x")

    def reset(self):
        """重置状态栏"""
        self.set_score(0)
        self.set_speed(200)
        self._is_paused = False
        self._pause_btn.setText("⏸ 暂停")
        self._pause_btn.setStyleSheet("""
            QPushButton {
                background: rgba(79, 195, 247, 0.2);
                border: 1px solid rgba(79, 195, 247, 0.4);
                border-radius: 16px;
                padding: 4px 16px;
                color: #4FC3F7;
                font-family: 'Microsoft YaHei', sans-serif;
                font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(79, 195, 247, 0.3);
            }
        """)

    def set_paused(self, paused: bool):
        """设置暂停状态"""
        if self._is_paused != paused:
            self._on_pause_clicked()