# -*- coding: utf-8 -*-
"""2048 插件自定义 Qt 组件

组件清单：
- TileButton: 数字格子按钮（支持弹出/闪烁/滑动动画）
- StatusBar: 状态栏（分数 + 最高分 + 新游戏按钮）
"""

from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, \
    pyqtSignal, pyqtProperty
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)


# ── 数字颜色映射（经典 2048 配色）──
TILE_COLORS = {
    0:     ("#CDC1B4", "#776E65"),
    2:     ("#EEE4DA", "#776E65"),
    4:     ("#EDE0C8", "#776E65"),
    8:     ("#F2B179", "#F9F6F2"),
    16:    ("#F59563", "#F9F6F2"),
    32:    ("#F67C5F", "#F9F6F2"),
    64:    ("#F65E3B", "#F9F6F2"),
    128:   ("#EDCF72", "#F9F6F2"),
    256:   ("#EDCC61", "#F9F6F2"),
    512:   ("#EDC850", "#F9F6F2"),
    1024:  ("#EDC53F", "#F9F6F2"),
    2048:  ("#EDC22E", "#F9F6F2"),
    4096:  ("#3C3A32", "#F9F6F2"),
    8192:  ("#3C3A32", "#F9F6F2"),
    16384: ("#3C3A32", "#F9F6F2"),
    32768: ("#3C3A32", "#F9F6F2"),
    65536: ("#3C3A32", "#F9F6F2"),
}


def get_tile_colors(value: int) -> tuple:
    """获取格子背景色和文字颜色"""
    if value in TILE_COLORS:
        return TILE_COLORS[value]
    return TILE_COLORS[max(k for k in TILE_COLORS if k <= value or k == 0)]


class TileButton(QPushButton):
    """2048 数字格子按钮，支持弹出与闪烁动画"""

    def __init__(self, x: int, y: int, size: int = 80, parent=None):
        super().__init__(parent)
        self._x = x
        self._y = y
        self._size = size
        self._value = 0
        self._is_new = False    # 新生成的格子（用于弹入动画）
        self._is_merged = False # 刚合并的格子（用于闪烁动画）

        self.setFixedSize(size, size)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCursor(Qt.ArrowCursor)
        self.setText("")
        self._update_appearance()

    def set_value(self, value: int, is_new: bool = False, is_merged: bool = False):
        """设置格子数值

        Args:
            value: 数字值（0 表示空白）
            is_new: 是否新生成的格子（触发弹入动画）
            is_merged: 是否刚合并的格子（触发闪烁动画）
        """
        self._value = value
        self._is_new = is_new
        self._is_merged = is_merged

        if value == 0:
            self.setText("")
        else:
            self.setText(str(value))

        self._update_appearance()

        # 触发动画
        if value != 0:
            if is_new or is_merged:
                QTimer.singleShot(10, self._play_appear_animation)

    def _update_appearance(self):
        """更新格子外观"""
        bg_color, text_color = get_tile_colors(self._value)

        if self._value == 0:
            font_size = 24
        elif self._value < 100:
            font_size = max(20, int(self._size * 0.45))
        elif self._value < 1000:
            font_size = max(18, int(self._size * 0.38))
        elif self._value < 10000:
            font_size = max(14, int(self._size * 0.3))
        else:
            font_size = max(12, int(self._size * 0.25))

        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg_color};
                border: none;
                border-radius: 6px;
                color: {text_color};
                font-weight: bold;
                font-size: {font_size}px;
            }}
        """)

    def _play_appear_animation(self):
        """弹出动画：先缩小再弹回正常大小"""
        if self._is_merged:
            # 合并闪烁：亮→暗 脉冲
            self._animate_pulse()
        else:
            # 新格子弹入：0.3 倍 → 1.1 倍 → 1.0 倍
            self._animate_scale_pop()

    def _animate_scale_pop(self):
        """三段式弹入动画"""
        # 第1步：缩到 0.3
        self._apply_scale(0.3)
        # 第2步：弹到 1.1（120ms）
        QTimer.singleShot(30, lambda: self._animate_to_scale(1.1, 80))
        # 第3步：回正 1.0（60ms）
        QTimer.singleShot(130, lambda: self._animate_to_scale(1.0, 50))

    def _animate_pulse(self):
        """合并闪烁：亮白 → 正常"""
        bg, _ = get_tile_colors(self._value)
        # 白色闪烁
        self.setStyleSheet(self.styleSheet() + f"""
            QPushButton {{
                background: #FFFFFF;
            }}
        """)
        # 100ms 后恢复
        QTimer.singleShot(100, self._update_appearance)

    def _apply_scale(self, scale: float):
        """通过内边距模拟缩放"""
        padding = int((1 - scale) * self._size / 2)
        self.setStyleSheet(self.styleSheet() + f"""
            QPushButton {{
                padding: {padding}px;
            }}
        """)

    def _animate_to_scale(self, target: float, duration: int):
        """用 QTimer 平滑缩放到目标比例"""
        steps = max(4, duration // 20)
        delta = (target - 0.3) / steps if target > 0.3 else (target - 1.1) / steps
        current = 0.3 if target > 0.3 else 1.1

        def step():
            nonlocal current
            current += delta
            if abs(current - target) < 0.01:
                self._apply_scale(target)
                return
            self._apply_scale(current)

        timer = QTimer(self)
        timer.timeout.connect(step)
        timer.setInterval(duration // steps)
        timer.setSingleShot(False)
        # 自动停止
        def stop():
            timer.stop()
            self._apply_scale(target)
        QTimer.singleShot(duration + 10, stop)
        timer.start()

    def get_value(self) -> int:
        return self._value

    def get_pos(self) -> tuple:
        return (self._x, self._y)


class StatusBar(QWidget):
    """状态栏：分数 | 最高分 | 新游戏按钮"""

    new_game_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        # 分数面板
        self._score_panel = self._make_score_panel("分数", "#EEE4DA")
        score_layout = self._score_panel.layout()
        self._score_label = QLabel("0", self._score_panel)
        self._score_label.setStyleSheet("""
            QLabel { color: #FFFFFF; font-size: 18px; font-weight: bold; min-width: 60px; }
        """)
        score_layout.addWidget(self._score_label)
        layout.addWidget(self._score_panel)

        # 最高分面板
        self._best_panel = self._make_score_panel("最高", "#F2B179")
        best_layout = self._best_panel.layout()
        self._best_label = QLabel("0", self._best_panel)
        self._best_label.setStyleSheet("""
            QLabel { color: #FFFFFF; font-size: 18px; font-weight: bold; min-width: 60px; }
        """)
        best_layout.addWidget(self._best_label)
        layout.addWidget(self._best_panel)

        layout.addStretch(1)

        # 新游戏按钮
        self._new_game_btn = QPushButton("新游戏", self)
        self._new_game_btn.setCursor(Qt.PointingHandCursor)
        self._new_game_btn.setStyleSheet("""
            QPushButton {
                background: #8F7A66; color: #F9F6F2; border: none;
                border-radius: 6px; padding: 6px 16px;
                font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background: #9F8B77; }
            QPushButton:pressed { background: #7F6A56; }
        """)
        self._new_game_btn.clicked.connect(self.new_game_clicked.emit)
        layout.addWidget(self._new_game_btn)

    def _make_score_panel(self, title: str, title_color: str) -> QWidget:
        panel = QWidget(self)
        panel.setStyleSheet("""
            QWidget { background: rgba(0,0,0,0.5); border-radius: 8px; padding: 4px 12px; }
        """)
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(8)
        lbl = QLabel(title, panel)
        lbl.setStyleSheet(f"color: {title_color}; font-size: 11px; font-weight: bold;")
        layout.addWidget(lbl)
        return panel

    def set_score(self, score: int):
        self._score_label.setText(str(score))

    def set_best_score(self, score: int):
        self._best_label.setText(str(score))

    def reset(self):
        self.set_score(0)
        self.set_best_score(0)
