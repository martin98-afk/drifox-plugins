# -*- coding: utf-8 -*-
"""贪吃蛇浮動卡片 — 在 DriFox 中直接玩经典贪吃蛇

功能：
- 方向键控制蛇的移动
- 空格键暂停/继续
- 吃食物生长并计分
- 撞墙/撞自身游戏结束
- 速度随蛇身长度递增
- 跟随 DriFox 主题色

设计约束：
- 不导入 app.core 或 app.widgets 内部的任何模块
- 游戏逻辑通过 game_logic.SnakeGame 实现
"""

from typing import Callable, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QKeyEvent
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

from .game_logic import SnakeGame, Direction, GameState, CollisionType
from .widgets import GameCanvas, StatusBar


# ── 游戏配置 ──
GRID_WIDTH = 15
GRID_HEIGHT = 15
CELL_SIZE = 28


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


class SnakeCard(QWidget):
    """贪吃蛇浮動卡片"""

    closed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context_provider: Optional[Callable[[], dict]] = None

        # 游戏逻辑
        self._game: Optional[SnakeGame] = None
        # 游戏画布
        self._canvas: Optional[GameCanvas] = None
        # 游戏定时器
        self._timer: Optional[QTimer] = None
        # 当前速度间隔
        self._current_interval: int = 200

        # UI 组件
        self._status_bar: Optional[StatusBar] = None
        self._title_label: Optional[StrongBodyLabel] = None

        # 游戏提示标签
        self._hint_label: Optional[QLabel] = None

        # 缓存的上下文值
        self._cached_tc = ""
        self._cached_tcs = ""
        self._cached_font_family = ""
        self._cached_font_size = 14

        self._setup_ui()
        self._init_game()

    # ── 上下文注入 ──

    def set_context_provider(self, provider: Callable[[], dict]):
        """注入上下文提供函数（由 UIPluginRegistry 调用）"""
        self._context_provider = provider

    def show_card(self):
        """卡片显示时：用最新上下文刷新主题色"""
        self._apply_latest_theme()
        self.setVisible(True)
        # 确保画布获得焦点以便接收键盘事件
        if self._canvas:
            self._canvas.setFocus()

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

        # 第 1 层：QFont 级联
        if font_family:
            self.setFont(QFont(font_family, font_size if font_size else 14))

        # 更新标题颜色
        if self._title_label:
            ss = f"color: {tc}; background: transparent;"
            if font_family:
                ss += f" font-family: '{font_family}';"
            if font_size:
                ss += f" font-size: {font_size}px;"
            self._title_label.setStyleSheet(ss)

        # 更新提示文字颜色
        if self._hint_label:
            hint_ss = f"color: {tcs}; background: transparent;"
            if font_family:
                hint_ss += f" font-family: '{font_family}';"
            if font_size:
                hint_ss += f" font-size: {font_size - 2}px;"
            self._hint_label.setStyleSheet(hint_ss)

        # 更新画布主题
        if self._canvas:
            self._canvas.update_theme(isDarkTheme())

    # ── UI 搭建 ──

    def _setup_ui(self):
        self.setMinimumHeight(0)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("SnakeCard { background: transparent; }")

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

        self._title_label = StrongBodyLabel("贪吃蛇", header)
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

        # 状态栏
        self._status_bar = StatusBar(content)
        self._status_bar.pause_clicked.connect(self._on_pause_clicked)
        self._status_bar.restart_clicked.connect(self._on_restart)
        content_layout.addWidget(self._status_bar)

        # 游戏提示
        self._hint_label = QLabel("方向键移动 | 空格暂停", content)
        self._hint_label.setAlignment(Qt.AlignCenter)
        self._hint_label.setStyleSheet(f"color: {_text_color(secondary=True)}; background: transparent;")
        content_layout.addWidget(self._hint_label)

        # 游戏画布
        self._canvas = GameCanvas(GRID_WIDTH, GRID_HEIGHT, CELL_SIZE, content)
        self._canvas.key_pressed.connect(self._on_key_pressed)
        content_layout.addWidget(self._canvas, 0, Qt.AlignCenter)

        root.addWidget(content, 1)

    # ── 游戏逻辑 ──

    def _init_game(self):
        """初始化游戏逻辑"""
        self._game = SnakeGame(GRID_WIDTH, GRID_HEIGHT)
        self._current_interval = 200

        # 创建定时器
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)

        # 重置状态
        self._status_bar.reset()

        # 初始化游戏状态（等待开始）
        self._update_display()

    def _start_game(self):
        """开始游戏"""
        if self._game.state == GameState.READY:
            self._game.start()
            self._current_interval = self._game.interval
            self._timer.start(self._current_interval)

    def _on_tick(self):
        """定时器触发：推进游戏"""
        if self._game is None or self._game.state != GameState.PLAYING:
            return

        result = self._game.tick()

        # 更新显示
        self._update_display()

        # 更新分数和速度
        self._status_bar.set_score(result["score"])
        self._status_bar.set_speed(result["interval"])

        # 检查游戏结束
        if result.get("game_over"):
            self._timer.stop()
            if result.get("won"):
                self._show_game_over("🎉 恭喜通关！")
            else:
                self._show_game_over("💀 游戏结束！")

        # 检查速度变化
        if result["interval"] != self._current_interval:
            self._current_interval = result["interval"]
            # 重启定时器以应用新速度
            self._timer.stop()
            self._timer.start(self._current_interval)

    def _update_display(self):
        """更新游戏画面"""
        if self._game is None or self._canvas is None:
            return

        state = self._game.get_state()
        self._canvas.set_game_data(state["snake"], state["food"])

    def _on_key_pressed(self, key: int):
        """处理键盘事件"""
        if self._game is None:
            return

        # 空格键：暂停/继续
        if key == Qt.Key_Space:
            self._on_pause_clicked()
            return

        # 游戏未开始时，按方向键开始游戏
        if self._game.state == GameState.READY:
            direction_map = {
                Qt.Key_Up: Direction.UP,
                Qt.Key_Down: Direction.DOWN,
                Qt.Key_Left: Direction.LEFT,
                Qt.Key_Right: Direction.RIGHT,
            }
            if key in direction_map:
                self._game.start()
                self._game.set_direction(direction_map[key])
                self._current_interval = self._game.interval
                self._timer.start(self._current_interval)
                self._update_display()
            return

        # 游戏未在运行时不处理方向键
        if self._game.state != GameState.PLAYING:
            return

        # 方向键控制
        direction_map = {
            Qt.Key_Up: Direction.UP,
            Qt.Key_Down: Direction.DOWN,
            Qt.Key_Left: Direction.LEFT,
            Qt.Key_Right: Direction.RIGHT,
            Qt.Key_W: Direction.UP,
            Qt.Key_S: Direction.DOWN,
            Qt.Key_A: Direction.LEFT,
            Qt.Key_D: Direction.RIGHT,
        }

        if key in direction_map:
            self._game.set_direction(direction_map[key])

    def _on_pause_clicked(self):
        """暂停/继续按钮点击"""
        if self._game is None:
            return

        if self._game.state == GameState.READY:
            # 快速开始
            self._game.start()
            self._current_interval = self._game.interval
            self._timer.start(self._current_interval)
            self._update_display()
            self._canvas.setFocus()
            return

        if self._game.state == GameState.WON or self._game.state == GameState.LOST:
            # 游戏结束时点击按钮相当于重新开始
            self._on_restart()
            return

        # 暂停/继续
        result = self._game.pause()
        if result["state"] == GameState.PAUSED:
            self._timer.stop()
            self._status_bar.set_paused(True)
        else:
            self._timer.start(self._current_interval)
            self._status_bar.set_paused(False)
        self._canvas.setFocus()

    def _on_restart(self):
        """重新开始游戏"""
        if self._game is None:
            return

        self._timer.stop()
        self._game.reset()
        self._current_interval = 200
        self._status_bar.reset()
        self._update_display()

        # 自动开始新游戏
        self._game.start()
        self._current_interval = self._game.interval
        self._timer.start(self._current_interval)
        self._update_display()

        self._canvas.setFocus()

    def _show_game_over(self, message: str):
        """显示游戏结束信息"""
        # 更新提示文字
        if self._hint_label:
            self._hint_label.setText(f"{message} 按「重开」再来一局！")

    # ── 关闭 ──

    def _on_close(self):
        self.setVisible(False)
        self.closed.emit()

    def deleteLater(self):
        if self._timer:
            self._timer.stop()
        super().deleteLater()