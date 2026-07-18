# -*- coding: utf-8 -*-
"""扫雷插件自定义 Qt 组件

组件清单：
- MineCellButton: 游戏格子按钮（支援左键/右键信号）
- StatusBar: 状态栏（地雷计数 + 笑臉按钮 + 计时器）
- DifficultySelector: 难度选择条
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


# ── 数字颜色映射（经典扫雷配色）──
NUMBER_COLORS = {
    1: "#4FC3F7",   # 蓝
    2: "#81C784",   # 绿
    3: "#E94560",   # 红
    4: "#BA68C8",   # 紫
    5: "#E53935",   # 深红
    6: "#00BCD4",   # 青
    7: "#424242",   # 黑
    8: "#9E9E9E",   # 灰
}


def _make_style(color: str, font_family: str = "", font_size: int = 0, extra: str = "") -> str:
    """生成带字体的 QSS 样式串"""
    parts = [f"color: {color};"]
    if font_family:
        parts.append(f"font-family: '{font_family}';")
    if font_size:
        parts.append(f"font-size: {font_size}px;")
    if extra:
        parts.append(extra)
    return " ".join(parts)


class MineCellButton(QPushButton):
    """游戏格子按钮

    支援：
    - 左键点击 → left_clicked 信号
    - 右键点击 → right_clicked 信号
    - 三种视觉状态：未翻开 / 已翻开 / 插旗
    """

    left_clicked = pyqtSignal(int, int)
    right_clicked = pyqtSignal(int, int)

    def __init__(self, x: int, y: int, cell_size: int = 32, parent=None):
        super().__init__(parent)
        self._x = x
        self._y = y
        self._cell_size = cell_size
        self._is_revealed = False
        self._is_flagged = False
        self._is_mine = False
        self._value = 0  # -1=mine, 0-8=number

        self.setFixedSize(cell_size, cell_size)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self._update_appearance()

    def set_cell_size(self, size: int):
        """更新格子尺寸"""
        self._cell_size = size
        self.setFixedSize(size, size)

    def set_cell_data(self, value: int, is_revealed: bool, is_flagged: bool, is_mine: bool):
        """更新格子数据"""
        self._value = value
        self._is_revealed = is_revealed
        self._is_flagged = is_flagged
        self._is_mine = is_mine
        self._update_appearance()

    def _update_appearance(self):
        """根据状态更新外观"""
        if self._is_revealed:
            if self._is_mine:
                self.setText("💣")
                self.setStyleSheet("""
                    QPushButton {
                        background: rgba(233, 69, 96, 0.3);
                        border: 1px solid rgba(233, 69, 96, 0.5);
                        border-radius: 3px;
                        font-size: 16px;
                    }
                """)
            elif self._value == 0:
                self.setText("")
                self.setStyleSheet("""
                    QPushButton {
                        background: rgba(128, 128, 128, 0.08);
                        border: 1px solid rgba(128, 128, 128, 0.05);
                        border-radius: 3px;
                    }
                """)
            else:
                # 数字
                color = NUMBER_COLORS.get(self._value, "#FFFFFF")
                fs = max(12, self._cell_size // 2)
                self.setText(str(self._value))
                self.setStyleSheet(f"""
                    QPushButton {{
                        background: rgba(128, 128, 128, 0.08);
                        border: 1px solid rgba(128, 128, 128, 0.05);
                        border-radius: 3px;
                        color: {color};
                        font-weight: bold;
                        font-size: {fs}px;
                    }}
                """)
        elif self._is_flagged:
            self.setText("🚩")
            self.setStyleSheet("""
                QPushButton {
                    background: rgba(233, 69, 96, 0.15);
                    border: 1px solid rgba(233, 69, 96, 0.3);
                    border-radius: 3px;
                    font-size: 14px;
                }
            """)
        else:
            # 未翻开
            self.setText("")
            self.setStyleSheet("""
                QPushButton {
                    background: rgba(128, 128, 128, 0.15);
                    border: 1px solid rgba(128, 128, 128, 0.1);
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background: rgba(128, 128, 128, 0.25);
                }
                QPushButton:pressed {
                    background: rgba(128, 128, 128, 0.35);
                }
            """)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """拦截鼠标事件，发送自定义信号"""
        if event.button() == Qt.LeftButton:
            self.left_clicked.emit(self._x, self._y)
        elif event.button() == Qt.RightButton:
            self.right_clicked.emit(self._x, self._y)
        # 不调用 super().mouseReleaseEvent 以避免触发 clicked 信号
        # 但需要调用 QPushButton 的 mouseReleaseEvent 以保持状态正确
        super().mouseReleaseEvent(event)


class StatusBar(QWidget):
    """状态栏：地雷计数 | 笑臉按钮 | 计时器"""

    smiley_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        # 地雷计数
        self._mine_counter = QLabel("000", self)
        self._mine_counter.setStyleSheet("""
            QLabel {
                color: #E94560;
                background: rgba(0, 0, 0, 0.6);
                padding: 2px 8px;
                border-radius: 4px;
                font-family: 'Courier New', monospace;
                font-size: 18px;
                font-weight: bold;
                letter-spacing: 2px;
            }
        """)
        layout.addWidget(self._mine_counter)

        layout.addStretch(1)

        # 笑臉按钮
        self._smiley_btn = QPushButton("🙂", self)
        self._smiley_btn.setFixedSize(36, 36)
        self._smiley_btn.setCursor(Qt.PointingHandCursor)
        self._smiley_btn.setStyleSheet("""
            QPushButton {
                background: rgba(128, 128, 128, 0.1);
                border: 2px solid rgba(128, 128, 128, 0.2);
                border-radius: 18px;
                font-size: 18px;
            }
            QPushButton:hover {
                background: rgba(128, 128, 128, 0.2);
            }
            QPushButton:pressed {
                background: rgba(128, 128, 128, 0.3);
            }
        """)
        self._smiley_btn.clicked.connect(self.smiley_clicked.emit)
        layout.addWidget(self._smiley_btn)

        layout.addStretch(1)

        # 计时器
        self._timer_label = QLabel("000", self)
        self._timer_label.setStyleSheet("""
            QLabel {
                color: #E94560;
                background: rgba(0, 0, 0, 0.6);
                padding: 2px 8px;
                border-radius: 4px;
                font-family: 'Courier New', monospace;
                font-size: 18px;
                font-weight: bold;
                letter-spacing: 2px;
            }
        """)
        layout.addWidget(self._timer_label)

    def set_mine_count(self, count: int):
        """更新地雷计数显示"""
        self._mine_counter.setText(f"{max(0, count):03d}")

    def set_time(self, seconds: int):
        """更新计时器显示"""
        self._timer_label.setText(f"{min(seconds, 999):03d}")

    def set_smiley(self, smiley: str):
        """更新笑臉表情

        🙂 游戏中  😎 胜利  😵 失败
        """
        self._smiley_btn.setText(smiley)

    def reset(self):
        """重置状态栏"""
        self.set_mine_count(0)
        self.set_time(0)
        self.set_smiley("🙂")


class DifficultySelector(QWidget):
    """难度选择条"""

    difficulty_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self._difficulties = [
            ("easy",   "初级",  "9×9"),
            ("medium", "中级",  "16×16"),
            ("hard",   "高级",  "30×16"),
        ]

        self._buttons = []
        for key, label, desc in self._difficulties:
            btn = QPushButton(f"{label} {desc}", self)
            btn.setProperty("difficulty", key)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, k=key: self._on_difficulty_clicked(k))
            btn.setStyleSheet(self._btn_style(False))
            layout.addWidget(btn)
            self._buttons.append(btn)

        # 默认选中中级
        self._selected = "medium"
        self._update_selection()

        layout.addStretch(1)

    def _btn_style(self, active: bool) -> str:
        if active:
            return """
                QPushButton {
                    background: rgba(233, 69, 96, 0.3);
                    border: 1px solid rgba(233, 69, 96, 0.6);
                    border-radius: 12px;
                    padding: 4px 12px;
                    color: #FFFFFF;
                    font-size: 12px;
                }
            """
        else:
            return """
                QPushButton {
                    background: rgba(128, 128, 128, 0.1);
                    border: 1px solid transparent;
                    border-radius: 12px;
                    padding: 4px 12px;
                    color: rgba(255, 255, 255, 0.6);
                    font-size: 12px;
                }
                QPushButton:hover {
                    background: rgba(128, 128, 128, 0.2);
                    color: rgba(255, 255, 255, 0.9);
                }
            """

    def _on_difficulty_clicked(self, key: str):
        if key != self._selected:
            self._selected = key
            self._update_selection()
            self.difficulty_changed.emit(key)

    def _update_selection(self):
        for btn in self._buttons:
            active = btn.property("difficulty") == self._selected
            btn.setChecked(active)
            btn.setStyleSheet(self._btn_style(active))

    def get_selected(self) -> str:
        return self._selected
