# -*- coding: utf-8 -*-
"""打砖块浮动卡片 — 在 DriFox 中直接玩经典打砖块

功能：
- 鼠标控制挡板移动
- 球反弹击碎砖块
- 计分系统
- 生命值（3条）
- 游戏结束/胜利判断
- 砖块颜色分层
- 跟随 DriFox 主题色

设计约束：
- 不导入 app.core 或 app.widgets 内部的任何模块
- 游戏逻辑通过 game_logic.BreakoutGame 实现
"""

from typing import Callable, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    FluentIcon,
    IconWidget,
    StrongBodyLabel,
    TransparentToolButton,
    isDarkTheme,
)
from loguru import logger

from .game_logic import BreakoutGame, GameState
from .widgets import (
    GameCanvas,
    StatusBar,
    ControlHint,
)


# ── 游戏区域配置 ──
GAME_WIDTH = 400
GAME_HEIGHT = 480
BRICK_ROWS = 5
BRICK_COLS = 8

# 帧率
FPS = 60


# ── 主题色辅助 ──

def _text_color(secondary: bool = False) -> str:
    """fallback 文字颜色（无上下文时使用）"""
    if isDarkTheme():
        return "rgba(255,255,255,0.55)" if secondary else "rgba(255,255,255,0.9)"
    return "rgba(0,0,0,0.45)" if secondary else "rgba(0,0,0,0.85)"


def _ctx_font(ctx: dict) -> tuple:
    """从上下文提取 font_family 和 font_size"""
    ff = ctx.get("font_family", "Microsoft YaHei")
    fs = ctx.get("font_size", 14)
    return ff, fs


def _ctx_text_color(ctx: dict, secondary: bool = False) -> str:
    """从上下文 colors 中获取文字颜色"""
    colors = ctx.get("colors", {})
    key = "text_secondary" if secondary else "text_primary"
    val = colors.get(key, "")
    if val:
        return val
    return _text_color(secondary)


class BreakoutCard(QWidget):
    """打砖块浮动卡片"""

    closed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context_provider: Optional[Callable[[], dict]] = None

        # 游戏引擎
        self._game = BreakoutGame(
            game_width=GAME_WIDTH,
            game_height=GAME_HEIGHT,
            rows=BRICK_ROWS,
            cols=BRICK_COLS
        )

        # 动画定时器
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_game_tick)
        self._timer.setInterval(1000 // FPS)  # 60 FPS

        # 键盘状态
        self._keys_pressed = set()
        # 鼠标追踪
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._setup_ui()
        self._update_display()

    # ── 上下文注入 ──

    def set_context_provider(self, provider: Callable[[], dict]):
        """注入上下文提供函数（由 UIPluginRegistry 调用）"""
        self._context_provider = provider

    def show_card(self):
        """卡片显示时：用最新上下文刷新主题色"""
        self._apply_latest_theme()
        self.setVisible(True)
        self.setFocus()  # 获取键盘焦点
        self._game_canvas.setFocus()

    def _apply_latest_theme(self):
        """从上下文拉取最新主题色并刷新全部子控件样式"""
        if self._context_provider is None:
            return
        try:
            ctx = self._context_provider()
        except Exception:
            return

        font_family, font_size = _ctx_font(ctx)
        tc = _ctx_text_color(ctx)
        tcs = _ctx_text_color(ctx, secondary=True)

        # 缓存上下文值
        self._cached_tc = tc
        self._cached_tcs = tcs
        self._cached_font_family = font_family
        self._cached_font_size = font_size

        # QFont 级联
        if font_family:
            self.setFont(QFont(font_family, font_size if font_size else 14))

        # 更新标题颜色
        if hasattr(self, '_title_label'):
            ss = f"color: {tc}; background: transparent;"
            if font_family:
                ss += f" font-family: '{font_family}';"
            if font_size:
                ss += f" font-size: {font_size}px;"
            self._title_label.setStyleSheet(ss)

    # ── UI 搭建 ──

    def _setup_ui(self):
        self.setMinimumHeight(0)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("BreakoutCard { background: transparent; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 头部 ──
        header = QWidget(self)
        header.setStyleSheet("background: transparent;")
        hly = QHBoxLayout(header)
        hly.setContentsMargins(16, 12, 16, 4)
        hly.setSpacing(8)

        ic = IconWidget(FluentIcon.GAME, header)
        ic.setFixedSize(22, 22)
        hly.addWidget(ic)

        self._title_label = StrongBodyLabel("打砖块", header)
        self._title_label.setStyleSheet(f"color: {_text_color()}; background: transparent;")
        hly.addWidget(self._title_label)

        hly.addStretch(1)

        close_btn = TransparentToolButton(FluentIcon.CLOSE, header)
        close_btn.setFixedSize(24, 24)
        close_btn.setToolTip("关闭")
        close_btn.clicked.connect(self._on_close)
        hly.addWidget(close_btn)

        root.addWidget(header)

        # ── 分隔线 ──
        sep = QLabel(self)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(128,128,128,0.15);")
        root.addWidget(sep)

        # ── 内容区域 ──
        content = QWidget(self)
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 8, 12, 12)
        content_layout.setSpacing(8)
        content_layout.setAlignment(Qt.AlignCenter)

        # 状态栏（分数、生命、按钮）
        self._status_bar = StatusBar(content)
        self._status_bar.start_clicked.connect(self._on_start_clicked)
        self._status_bar.restart_clicked.connect(self._on_restart)
        content_layout.addWidget(self._status_bar)

        # 游戏画布
        self._game_canvas = GameCanvas(GAME_WIDTH, GAME_HEIGHT, content)
        content_layout.addWidget(self._game_canvas, 0, Qt.AlignCenter)

        # 操作提示
        self._hint_widget = ControlHint(content)
        content_layout.addWidget(self._hint_widget, 0, Qt.AlignCenter)

        root.addWidget(content, 1)

    # ── 游戏控制 ──

    def _on_start_clicked(self):
        """开始按钮点击"""
        if self._game.state == GameState.READY:
            self._game.start()
            self._timer.start()
        elif self._game.state == GameState.PLAYING:
            self._game.launch_ball()

    def _on_restart(self):
        """重新开始游戏"""
        self._timer.stop()
        self._game.reset()
        self._status_bar.reset()
        self._update_display()

    def _on_game_tick(self):
        """游戏每帧更新"""
        if self._game.state != GameState.PLAYING:
            return

        # 处理键盘输入
        if "left" in self._keys_pressed:
            self._game.move_paddle("left")
        if "right" in self._keys_pressed:
            self._game.move_paddle("right")

        # 更新游戏逻辑
        result = self._game.update()

        # 更新显示
        self._update_display()

        # 处理游戏结束
        if result.get("game_over"):
            self._timer.stop()
            self._status_bar.show_restart_button()

        # 处理生命损失（重置到 READY 状态）
        if result.get("life_lost"):
            self._status_bar.show_start_button()

    def _update_display(self):
        """更新游戏画面显示"""
        state = self._game.get_state()
        self._game_canvas.set_game_data(state)
        self._status_bar.set_score(state["score"])
        self._status_bar.set_lives(state["lives"])

    # ── 鼠标控制 ──

    def mouse_move_handler(self, x: int):
        """处理鼠标移动（控制挡板）"""
        if self._game.state in (GameState.PLAYING, GameState.READY):
            # x 已由 canvas 转发，是画布内相对坐标
            self._game.set_paddle_position(x)

    def mouse_click_handler(self):
        """处理鼠标点击"""
        if self._game.state == GameState.READY:
            self._game.launch_ball()
        elif self._game.state == GameState.WON or self._game.state == GameState.LOST:
            self._on_restart()

    # ── 键盘控制 ──

    def keyPressEvent(self, event):
        """键盘按下"""
        key = event.key()
        if key == Qt.Key_Left or key == Qt.Key_A:
            self._keys_pressed.add("left")
        elif key == Qt.Key_Right or key == Qt.Key_D:
            self._keys_pressed.add("right")
        elif key == Qt.Key_Space:
            if self._game.state == GameState.READY:
                self._game.launch_ball()
            elif self._game.state == GameState.PLAYING:
                pass  # 游戏中空格无操作
        elif key == Qt.Key_R:
            self._on_restart()
        event.accept()

    def keyReleaseEvent(self, event):
        """键盘释放"""
        key = event.key()
        if key == Qt.Key_Left or key == Qt.Key_A:
            self._keys_pressed.discard("left")
        elif key == Qt.Key_Right or key == Qt.Key_D:
            self._keys_pressed.discard("right")
        event.accept()

    # ── 鼠标控制（由 GameCanvas 转发调用）──

    # ── 关闭 ──

    def _on_close(self):
        self._timer.stop()
        self.setVisible(False)
        self.closed.emit()

    def deleteLater(self):
        self._timer.stop()
        super().deleteLater()