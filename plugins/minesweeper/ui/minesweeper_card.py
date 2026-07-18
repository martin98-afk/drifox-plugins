# -*- coding: utf-8 -*-
"""扫雷浮動卡片 — 在 DriFox 中直接玩经典扫雷

功能：
- 三种难度自由切换
- 左键翻开、右键插旗
- 首次点击安全保护
- 计时器 & 地雷计数
- 跟随 DriFox 主题色

设计约束：
- 不导入 app.core 或 app.widgets 内部的任何模块
- 游戏逻辑通过 game_logic.MinesweeperGame 实现
"""

from typing import Callable, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QGridLayout,
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
    ToolButton,
    TransparentToolButton,
    isDarkTheme,
)
from loguru import logger

from .game_logic import MinesweeperGame, CellState, GameState
from .widgets import (
    MineCellButton,
    StatusBar,
    DifficultySelector,
)


# ── 难度配置 ──
DIFFICULTIES = {
    "easy":   {"width": 9, "height": 9, "mines": 10,  "cell_size": 36},
    "medium": {"width": 16, "height": 16, "mines": 40, "cell_size": 30},
    "hard":   {"width": 30, "height": 16, "mines": 99, "cell_size": 24},
}


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


class MinesweeperCard(QWidget):
    """扫雷浮動卡片"""

    closed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context_provider: Optional[Callable[[], dict]] = None

        # 游戏状态
        self._game: Optional[MinesweeperGame] = None
        self._difficulty = "medium"
        self._buttons: list[list[MineCellButton]] = []
        self._timer_seconds = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer_tick)
        self._game_started = False

        self._setup_ui()
        self._new_game()

    # ── 上下文注入 ──

    def set_context_provider(self, provider: Callable[[], dict]):
        """注入上下文提供函数（由 UIPluginRegistry 调用）"""
        self._context_provider = provider

    def show_card(self):
        """卡片显示时：用最新上下文刷新主题色"""
        self._apply_latest_theme()
        self.setVisible(True)

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
        if hasattr(self, '_title_label'):
            ss = f"color: {tc}; background: transparent;"
            if font_family:
                ss += f" font-family: '{font_family}';"
            if font_size:
                ss += f" font-size: {font_size}px;"
            self._title_label.setStyleSheet(ss)

        # 刷新所有已创建的按钮外观
        for row in self._buttons:
            for btn in row:
                btn._update_appearance()

    # ── UI 搭建 ──

    def _setup_ui(self):
        self.setMinimumHeight(0)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("MinesweeperCard { background: transparent; }")

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

        self._title_label = StrongBodyLabel("💣 扫雷", header)
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
        self._status_bar.smiley_clicked.connect(self._on_smiley_clicked)
        content_layout.addWidget(self._status_bar)

        # 游戏网各容器
        self._grid_container = QWidget(content)
        self._grid_container.setObjectName("gridContainer")
        self._grid_container.setStyleSheet("QWidget#gridContainer { background: transparent; }")
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(2)
        self._grid_layout.setContentsMargins(4, 4, 4, 4)
        content_layout.addWidget(self._grid_container, 0, Qt.AlignCenter)

        # 难度选择
        self._difficulty_selector = DifficultySelector(content)
        self._difficulty_selector.difficulty_changed.connect(self._on_difficulty_changed)
        content_layout.addWidget(self._difficulty_selector, 0, Qt.AlignCenter)

        root.addWidget(content, 1)

    # ── 游戏逻辑 ──

    def _new_game(self):
        """开始新游戏"""
        diff = DIFFICULTIES[self._difficulty]
        self._game = MinesweeperGame(diff["width"], diff["height"], diff["mines"])
        self._game_started = False
        self._timer_seconds = 0
        self._timer.stop()

        # 更新状态栏
        self._status_bar.reset()
        self._status_bar.set_mine_count(diff["mines"])

        # 重建网各
        self._rebuild_board(diff["cell_size"])

    def _rebuild_board(self, cell_size: int):
        """重建游戏网各按钮"""
        # 清除旧按钮
        for btn_list in self._buttons:
            for btn in btn_list:
                self._grid_layout.removeWidget(btn)
                btn.deleteLater()
        self._buttons = []

        diff = DIFFICULTIES[self._difficulty]
        w, h = diff["width"], diff["height"]

        for x in range(w):
            row = []
            for y in range(h):
                btn = MineCellButton(x, y, cell_size, self._grid_container)
                btn.left_clicked.connect(self._on_cell_left_click)
                btn.right_clicked.connect(self._on_cell_right_click)
                self._grid_layout.addWidget(btn, y, x)
                row.append(btn)
            self._buttons.append(row)

    def _on_cell_left_click(self, x: int, y: int):
        """左键点击格子"""
        if self._game is None:
            return
        if self._game.state == GameState.WON or self._game.state == GameState.LOST:
            return

        result = self._game.reveal(x, y)
        self._sync_board(result.get("changed", []))

        # 首次点击启动计时器
        if not self._game_started and self._game._initialized:
            self._game_started = True
            self._timer.start(1000)

        # 处理游戏结束
        if result.get("game_over"):
            self._timer.stop()
            if result.get("won"):
                self._status_bar.set_smiley("😎")
            else:
                self._status_bar.set_smiley("😵")

        # 更新地雷计数
        diff = DIFFICULTIES[self._difficulty]
        self._status_bar.set_mine_count(diff["mines"] - self._game.flag_count)

    def _on_cell_right_click(self, x: int, y: int):
        """右键点击格子（插旗）"""
        if self._game is None:
            return
        if self._game.state == GameState.WON or self._game.state == GameState.LOST:
            return

        result = self._game.toggle_flag(x, y)

        # 更新按钮显示
        cell = self._game.get_cell(x, y)
        if x < len(self._buttons) and y < len(self._buttons[x]):
            btn = self._buttons[x][y]
            btn.set_cell_data(
                value=cell["value"],
                is_revealed=cell["state"] == CellState.REVEALED,
                is_flagged=cell["state"] == CellState.FLAGGED,
                is_mine=cell["is_mine"],
            )

        # 更新地雷计数
        diff = DIFFICULTIES[self._difficulty]
        self._status_bar.set_mine_count(diff["mines"] - self._game.flag_count)

    def _sync_board(self, changed_cells: list):
        """同步变化的格子到 UI"""
        for cx, cy, value, is_mine in changed_cells:
            if cx < len(self._buttons) and cy < len(self._buttons[cx]):
                btn = self._buttons[cx][cy]
                cell = self._game.get_cell(cx, cy)
                btn.set_cell_data(
                    value=cell["value"],
                    is_revealed=cell["state"] == CellState.REVEALED,
                    is_flagged=cell["state"] == CellState.FLAGGED,
                    is_mine=cell["is_mine"],
                )

    def _on_smiley_clicked(self):
        """笑臉按钮点击 → 重置游戏"""
        self._new_game()

    def _on_difficulty_changed(self, difficulty: str):
        """难度切换"""
        self._difficulty = difficulty
        self._new_game()

    def _on_timer_tick(self):
        """计时器每秒更新"""
        self._timer_seconds += 1
        self._status_bar.set_time(self._timer_seconds)

    # ── 关闭 ──

    def _on_close(self):
        self.setVisible(False)
        self.closed.emit()

    def deleteLater(self):
        self._timer.stop()
        super().deleteLater()
