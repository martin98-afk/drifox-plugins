# -*- coding: utf-8 -*-
"""记忆翻牌浮动卡片 — 在 DriFox 中直接玩经典记忆翻牌

功能：
- 三种难度自由切换（4×4 / 4×6 / 5×6）
- 点击翻牌，最多两张同时翻开
- 配对成功自动消除
- 配对失败延迟翻回
- 步数统计、配对进度、计时器
- 跟随 DriFox 主题色

设计约束：
- 不导入 app.core 或 app.widgets 内部的任何模块
- 游戏逻辑通过 game_logic.MemoryMatchGame 实现
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
    TransparentToolButton,
    isDarkTheme,
)
from loguru import logger

from .game_logic import MemoryMatchGame, CardState, GameState
from .widgets import (
    FlipableCard,
    MemoryStatusBar,
    MemoryDifficultySelector,
    DIFFICULTIES,
)


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


class MemoryMatchCard(QWidget):
    """记忆翻牌浮动卡片"""

    closed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context_provider: Optional[Callable[[], dict]] = None

        # 游戏状态
        self._game: Optional[MemoryMatchGame] = None
        self._difficulty = "easy"
        self._cards: list[list[FlipableCard]] = []
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer_tick)
        self._game_started = False
        # 等待翻回动画的配对位置
        self._pending_flip_back: tuple = None

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

        # 字体
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

        # 刷新所有卡牌外观
        for row in self._cards:
            for card in row:
                card.style().unpolish(card)
                card.style().polish(card)

    # ── UI 搭建 ──

    def _setup_ui(self):
        self.setMinimumHeight(0)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("MemoryMatchCard { background: transparent; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 头部 ──
        header = QWidget(self)
        header.setStyleSheet("background: transparent;")
        hly = QHBoxLayout(header)
        hly.setContentsMargins(16, 12, 16, 4)
        hly.setSpacing(8)

        ic = IconWidget(FluentIcon.TILES, header)
        ic.setFixedSize(22, 22)
        hly.addWidget(ic)

        self._title_label = StrongBodyLabel("记忆翻牌", header)
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
        self._status_bar = MemoryStatusBar(content)
        content_layout.addWidget(self._status_bar)

        # 游戏网格容器
        self._grid_container = QWidget(content)
        self._grid_container.setObjectName("gridContainer")
        self._grid_container.setStyleSheet("QWidget#gridContainer { background: transparent; }")
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(6)
        self._grid_layout.setContentsMargins(4, 4, 4, 4)
        content_layout.addWidget(self._grid_container, 0, Qt.AlignCenter)

        # 难度选择
        self._difficulty_selector = MemoryDifficultySelector(content)
        self._difficulty_selector.difficulty_changed.connect(self._on_difficulty_changed)
        content_layout.addWidget(self._difficulty_selector, 0, Qt.AlignCenter)

        root.addWidget(content, 1)

    # ── 游戏逻辑 ──

    def _new_game(self):
        """开始新游戏"""
        diff = DIFFICULTIES[self._difficulty]
        self._game = MemoryMatchGame(diff["rows"], diff["cols"])
        self._game.start()
        self._game_started = False
        self._timer.stop()
        self._pending_flip_back = None

        # 更新状态栏
        self._status_bar.reset(diff["pairs"])
        self._status_bar.set_pairs(0, diff["pairs"])

        # 重建网格
        self._rebuild_board(diff["cell_size"])

    def _rebuild_board(self, cell_size: int):
        """重建游戏网格按钮"""
        # 清除旧按钮
        for row in self._cards:
            for card in row:
                self._grid_layout.removeWidget(card)
                card.deleteLater()
        self._cards = []

        diff = DIFFICULTIES[self._difficulty]
        rows, cols = diff["rows"], diff["cols"]

        for r in range(rows):
            row = []
            for c in range(cols):
                card = FlipableCard(r, c, cell_size, self._grid_container)
                card.clicked_card.connect(self._on_card_clicked)
                self._grid_layout.addWidget(card, r, c)
                row.append(card)
            self._cards.append(row)

    def _on_card_clicked(self, row: int, col: int):
        """点击卡牌"""
        if self._game is None:
            return
        if self._game.state == GameState.WON:
            return
        # 正在等待翻回动画时不响应
        if self._game.state == GameState.WAITING:
            return

        result = self._game.flip(row, col)
        changed = result.get("changed", [])

        # 更新卡牌状态
        for cr, cc, emoji, state, is_match in changed:
            if cr < len(self._cards) and cc < len(self._cards[cr]):
                card = self._cards[cr][cc]
                if state == CardState.MATCHED:
                    # 配对成功，带动画消除
                    card.set_matched(emoji)
                elif state == CardState.FLIPPED:
                    # 翻开
                    card.flip_to_front(emoji, matched=False)
                else:
                    card.flip_to_back()

        # 首次翻牌启动计时器
        if not self._game_started and self._game.state == GameState.PLAYING:
            self._game_started = True
            self._timer.start(1000)

        # 处理配对结果
        if result.get("is_match") is True:
            # 配对成功
            self._status_bar.set_pairs(self._game.matched_pairs, self._game.total_pairs)
        elif result.get("is_match") is False:
            # 配对失败，延迟翻回
            first = result.get("first_card")
            second = result.get("second_card")
            if first and second:
                self._pending_flip_back = (first, second)
                QTimer.singleShot(1000, self._do_flip_back)

        # 更新步数
        self._status_bar.set_moves(self._game.moves)

        # 处理游戏结束
        if result.get("game_over") and result.get("won"):
            self._timer.stop()
            self._show_win_animation()

    def _do_flip_back(self):
        """执行翻回动画"""
        if self._pending_flip_back is None:
            return
        first, second = self._pending_flip_back
        self._pending_flip_back = None

        # 翻转回背面
        fr, fc = first
        sr, sc = second
        if fr < len(self._cards) and fc < len(self._cards[fr]):
            self._cards[fr][fc].flip_to_back()
        if sr < len(self._cards) and sc < len(self._cards[sr]):
            self._cards[sr][sc].flip_to_back()

        # 更新游戏状态
        self._game.flip_back_pair(fr, fc, sr, sc)

    def _show_win_animation(self):
        """胜利动画：所有卡牌脉冲"""
        for row in self._cards:
            for card in row:
                card._animate_match()
                QTimer.singleShot(100, lambda c=card: c._animate_match() if hasattr(c, '_animate_match') else None)

    def _on_timer_tick(self):
        """计时器每秒更新"""
        if self._game:
            self._game.seconds += 1
            self._status_bar.set_time(self._game.seconds)

    def _on_difficulty_changed(self, difficulty: str):
        """难度切换"""
        self._difficulty = difficulty
        self._new_game()

    # ── 关闭 ──

    def _on_close(self):
        self.setVisible(False)
        self.closed.emit()

    def deleteLater(self):
        self._timer.stop()
        super().deleteLater()