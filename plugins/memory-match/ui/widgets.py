# -*- coding: utf-8 -*-
"""记忆翻牌插件自定义 Qt 组件

组件清单：
- MemoryCardButton: 卡牌按钮（支持翻转动画、左键/右键信号）
- StatusBar: 状态栏（步数 + 配对计数 + 计时器）
- DifficultySelector: 难度选择条
"""

from PyQt5.QtCore import Qt, QPropertyAnimation, pyqtSignal, pyqtProperty
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)


# ── 难度配置 ──
DIFFICULTIES = {
    "easy":   {"rows": 4, "cols": 4, "pairs": 8,  "cell_size": 64},   # 4×4 = 8对
    "medium": {"rows": 4, "cols": 6, "pairs": 12, "cell_size": 54},   # 4×6 = 12对
    "hard":   {"rows": 5, "cols": 6, "pairs": 15, "cell_size": 48},   # 5×6 = 15对
}


class FlipableCard(QPushButton):
    """可翻转的卡牌按钮

    特性：
    - 正面显示 emoji，背面显示图案
    - 翻转动画（左→右 3D 旋转）
    - 左键点击信号
    """

    clicked_card = pyqtSignal(int, int)  # row, col

    def __init__(self, row: int, col: int, cell_size: int = 64, parent=None):
        super().__init__(parent)
        self._row = row
        self._col = col
        self._cell_size = cell_size
        self._is_flipped = False
        self._is_matched = False
        self._emoji = ""
        self._animating = False

        self.setFixedSize(cell_size, cell_size)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)

        # 背面样式
        self._set_back_style()

    def _set_back_style(self):
        """设置背面样式"""
        self.setText("🂠")
        self.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #6366F1, stop:1 #8B5CF6);
                border: 2px solid rgba(255, 255, 255, 0.3);
                border-radius: 8px;
                font-size: {max(20, self._cell_size // 3)}px;
                color: white;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #818CF8, stop:1 #A78BFA);
            }}
        """)

    def _set_front_style(self, emoji: str, matched: bool = False):
        """设置正面样式"""
        if matched:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(34, 197, 94, 0.2);
                    border: 2px solid rgba(34, 197, 94, 0.5);
                    border-radius: 8px;
                    font-size: {max(24, self._cell_size // 2)}px;
                    color: #22C55E;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(255, 255, 255, 0.95);
                    border: 2px solid rgba(99, 102, 241, 0.5);
                    border-radius: 8px;
                    font-size: {max(24, self._cell_size // 2)}px;
                    color: #1F2937;
                }}
                QPushButton:hover {{
                    background: rgba(255, 255, 255, 1);
                    border: 2px solid rgba(99, 102, 241, 0.8);
                }}
            """)

    def flip_to_front(self, emoji: str, matched: bool = False, duration: int = 300):
        """翻转动画：背面 → 正面"""
        if self._animating:
            return
        self._animating = True
        self._emoji = emoji
        self._is_matched = matched

        # 使用动画模拟翻转效果
        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(duration // 2)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self._on_flip_midpoint_front)
        self._anim.start()

    def _on_flip_midpoint_front(self):
        """翻转中途：切换内容"""
        self._is_flipped = True
        self.setText(self._emoji)
        self._set_front_style(self._emoji, self._is_matched)
        self.setStyleSheet(self.styleSheet())  # 强制刷新

        # 下半场：淡入
        self._anim2 = QPropertyAnimation(self, b"windowOpacity")
        self._anim2.setDuration(150)
        self._anim2.setStartValue(0.0)
        self._anim2.setEndValue(1.0)
        self._anim2.finished.connect(self._on_flip_complete)
        self._anim2.start()

    def flip_to_back(self, duration: int = 300):
        """翻转动画：正面 → 背面"""
        if self._animating or not self._is_flipped:
            return
        self._animating = True

        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(duration // 2)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self._on_flip_midpoint_back)
        self._anim.start()

    def _on_flip_midpoint_back(self):
        """翻转中途：切换回背面"""
        self._is_flipped = False
        self.setText("🂠")
        self._set_back_style()

        self._anim2 = QPropertyAnimation(self, b"windowOpacity")
        self._anim2.setDuration(150)
        self._anim2.setStartValue(0.0)
        self._anim2.setEndValue(1.0)
        self._anim2.finished.connect(self._on_flip_complete)
        self._anim2.start()

    def _on_flip_complete(self):
        """翻转完成"""
        self._animating = False

    def set_immediate(self, emoji: str, flipped: bool, matched: bool = False):
        """立即设置状态（无动画，用于消除等场景）"""
        self._emoji = emoji
        self._is_flipped = flipped
        self._is_matched = matched
        if flipped or matched:
            self.setText(emoji)
            self._set_front_style(emoji, matched)
        else:
            self.setText("🂠")
            self._set_back_style()

    def set_matched(self, emoji: str):
        """设置为已配对状态（带完成动画）"""
        self._emoji = emoji
        self._is_matched = True
        self._is_flipped = True
        self.setText(emoji)
        self._set_front_style(emoji, matched=True)
        # 配对成功时加个脉冲动画效果
        self._animate_match()

    def _animate_match(self):
        """配对成功时的脉冲动画"""
        self._pulse_anim = QPropertyAnimation(self, b"windowOpacity")
        self._pulse_anim.setDuration(400)
        self._pulse_anim.setKeyValueAt(0, 1.0)
        self._pulse_anim.setKeyValueAt(0.5, 0.6)
        self._pulse_anim.setKeyValueAt(1, 1.0)
        self._pulse_anim.start()

    def mouseReleaseEvent(self, event: QMouseEvent):
        """拦截点击事件"""
        if event.button() == Qt.LeftButton and not self._animating:
            self.clicked_card.emit(self._row, self._col)
        super().mouseReleaseEvent(event)

    def is_animating(self) -> bool:
        return self._animating


class MemoryStatusBar(QWidget):
    """状态栏：步数 | 配对进度 | 计时器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        # 步数计数
        self._moves_label = QLabel("步数: 0", self)
        self._moves_label.setStyleSheet("""
            QLabel {
                color: #8B5CF6;
                background: rgba(99, 102, 241, 0.1);
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 13px;
                font-weight: 500;
                min-width: 80px;
            }
        """)
        layout.addWidget(self._moves_label)

        layout.addStretch(1)

        # 配对进度
        self._pairs_label = QLabel("0 / 8", self)
        self._pairs_label.setStyleSheet("""
            QLabel {
                color: #22C55E;
                background: rgba(34, 197, 94, 0.1);
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 13px;
                font-weight: 600;
                min-width: 70px;
                text-align: center;
            }
        """)
        layout.addWidget(self._pairs_label)

        layout.addStretch(1)

        # 计时器
        self._timer_label = QLabel("⏱ 0:00", self)
        self._timer_label.setStyleSheet("""
            QLabel {
                color: #6366F1;
                background: rgba(99, 102, 241, 0.1);
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 13px;
                font-weight: 500;
                min-width: 70px;
            }
        """)
        layout.addWidget(self._timer_label)

    def set_moves(self, moves: int):
        """更新步数"""
        self._moves_label.setText(f"步数: {moves}")

    def set_pairs(self, matched: int, total: int):
        """更新配对进度"""
        self._pairs_label.setText(f"{matched} / {total}")

    def set_time(self, seconds: int):
        """更新计时器"""
        mins = seconds // 60
        secs = seconds % 60
        self._timer_label.setText(f"⏱ {mins}:{secs:02d}")

    def reset(self, total_pairs: int = 8):
        """重置状态栏"""
        self.set_moves(0)
        self.set_pairs(0, total_pairs)
        self.set_time(0)


class MemoryDifficultySelector(QWidget):
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
            ("easy",   "初级",  "4×4"),
            ("medium", "中级",  "4×6"),
            ("hard",   "高级",  "5×6"),
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

        # 默认选中初级
        self._selected = "easy"
        self._update_selection()

        layout.addStretch(1)

    def _btn_style(self, active: bool) -> str:
        if active:
            return """
                QPushButton {
                    background: rgba(139, 92, 246, 0.3);
                    border: 1px solid rgba(139, 92, 246, 0.6);
                    border-radius: 12px;
                    padding: 4px 12px;
                    color: #FFFFFF;
                    font-size: 12px;
                    font-weight: 500;
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