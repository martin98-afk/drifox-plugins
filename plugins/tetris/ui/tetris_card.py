# -*- coding: utf-8 -*-
"""俄罗斯方块浮動卡片 — 在 DriFox 中直接玩经典俄罗斯方块

功能：
- 方向键移动/旋转，空格硬降，P 暂停
- 下一块预览
- 计分/等级/消除行显示
- 速度随等级递增
- 幽灵方块（落点预览）
- 跟随 DriFox 主题色

设计约束：
- 不导入 app.core 或 app.widgets 内部的任何模块
- 游戏逻辑通过 game_logic.TetrisGame 实现
"""

from typing import Callable, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
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

from .game_logic import TetrisGame, GameState, TETROMINOES
from .widgets import (
    TetrisBoardCanvas,
    PreviewCanvas,
    StatusBar,
    ControlHints,
)


# ── 主题色辅助 ──

def _text_color(secondary: bool = False) -> str:
    if isDarkTheme():
        return "rgba(255,255,255,0.55)" if secondary else "rgba(255,255,255,0.9)"
    return "rgba(0,0,0,0.45)" if secondary else "rgba(0,0,0,0.85)"


def _ctx_font(ctx: dict) -> tuple:
    ff = ctx.get("font_family", "Microsoft YaHei")
    fs = ctx.get("font_size", 14)
    return ff, fs


def _ctx_text_color(ctx: dict, secondary: bool = False) -> str:
    colors = ctx.get("colors", {})
    key = "text_secondary" if secondary else "text_primary"
    val = colors.get(key, "")
    if val:
        return val
    return _text_color(secondary)


class TetrisCard(QWidget):
    """俄罗斯方块浮動卡片"""

    closed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context_provider: Optional[Callable[[], dict]] = None

        # 游戏核心
        self._game = TetrisGame(width=10, height=20)
        self._auto_drop_timer = QTimer(self)
        self._auto_drop_timer.timeout.connect(self._on_auto_drop)

        # 初始启动状态（用户点击开始后才 PLAYING）
        self._game.reset()

        self._setup_ui()
        # 初始刷新
        self._sync_board()

    # ── 上下文注入 ──

    def set_context_provider(self, provider: Callable[[], dict]):
        self._context_provider = provider

    def show_card(self):
        self._apply_latest_theme()
        self.setVisible(True)
        # 聚焦画布以接收键盘
        if hasattr(self, "_board_canvas"):
            self._board_canvas.setFocus()

    def _apply_latest_theme(self):
        if self._context_provider is None:
            return
        try:
            ctx = self._context_provider()
        except Exception:
            return

        font_family, font_size = _ctx_font(ctx)
        tc = _ctx_text_color(ctx)
        tcs = _ctx_text_color(ctx, secondary=True)

        self._cached_tc = tc
        self._cached_tcs = tcs
        self._cached_font_family = font_family
        self._cached_font_size = font_size

        if font_family:
            self.setFont(QFont(font_family, font_size if font_size else 14))

        if hasattr(self, "_title_label"):
            ss = f"color: {tc}; background: transparent;"
            if font_family:
                ss += f" font-family: '{font_family}';"
            if font_size:
                ss += f" font-size: {font_size}px;"
            self._title_label.setStyleSheet(ss)

        # 刷新画布主题
        if hasattr(self, "_board_canvas"):
            self._board_canvas.set_theme(isDarkTheme())

    # ── UI 搭建 ──

    def _setup_ui(self):
        self.setMinimumHeight(0)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("TetrisCard { background: transparent; }")

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

        self._title_label = StrongBodyLabel("俄罗斯方块", header)
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

        # 游戏主区域：棋盘 + 侧边栏
        game_row = QWidget(content)
        game_row.setStyleSheet("background: transparent;")
        game_row_layout = QHBoxLayout(game_row)
        game_row_layout.setContentsMargins(0, 0, 0, 0)
        game_row_layout.setSpacing(12)

        # 棋盘
        self._board_canvas = TetrisBoardCanvas(
            board_width=10, board_height=20, cell_size=26, parent=game_row
        )
        self._board_canvas.left_pressed.connect(self._on_left)
        self._board_canvas.right_pressed.connect(self._on_right)
        self._board_canvas.up_pressed.connect(self._on_rotate)
        self._board_canvas.down_pressed.connect(self._on_soft_drop)
        self._board_canvas.space_pressed.connect(self._on_hard_drop)
        self._board_canvas.pause_pressed.connect(self._on_pause)
        self._board_canvas.clearing_done.connect(self._on_clearing_done)
        game_row_layout.addWidget(self._board_canvas)

        # 侧边栏
        sidebar = QWidget(game_row)
        sidebar.setStyleSheet("background: transparent;")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(10)

        # 开始/重新开始按钮
        self._start_btn = QPushButton("▶ 开始", sidebar)
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.setStyleSheet("""
            QPushButton {
                background: rgba(76, 175, 80, 0.3);
                border: 1px solid rgba(76, 175, 80, 0.6);
                border-radius: 14px;
                padding: 6px 16px;
                color: rgba(255,255,255,0.9);
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(76, 175, 80, 0.5);
            }
        """)
        self._start_btn.clicked.connect(self._on_start_clicked)
        sidebar_layout.addWidget(self._start_btn)

        # 下一块预览
        preview_lbl = QLabel("下一块", sidebar)
        preview_lbl.setStyleSheet("""
            QLabel {
                color: rgba(255,255,255,0.5);
                font-size: 12px;
                background: transparent;
            }
        """)
        sidebar_layout.addWidget(preview_lbl)

        self._preview_canvas = PreviewCanvas(size=100, parent=sidebar)
        sidebar_layout.addWidget(self._preview_canvas)

        # 状态栏
        self._status_bar = StatusBar(sidebar)
        sidebar_layout.addWidget(self._status_bar)

        sidebar_layout.addStretch(1)

        # 按键提示
        self._control_hints = ControlHints(sidebar)
        sidebar_layout.addWidget(self._control_hints)

        game_row_layout.addWidget(sidebar)
        content_layout.addWidget(game_row, 0, Qt.AlignCenter)

        root.addWidget(content, 1)

    # ── 游戏控制 ──

    def _on_start_clicked(self):
        """开始/重新开始按钮"""
        if self._game.state == GameState.GAME_OVER:
            self._game.reset()
        if self._game.state == GameState.READY:
            self._game.start()
            self._start_auto_drop()
            self._start_btn.setText("⏸ 暂停")
        elif self._game.state == GameState.PLAYING:
            self._game.pause()
            self._auto_drop_timer.stop()
            self._start_btn.setText("▶ 继续")
        elif self._game.state == GameState.PAUSED:
            self._game.pause()
            self._start_auto_drop()
            self._start_btn.setText("⏸ 暂停")
        self._sync_board()

    def _start_auto_drop(self):
        interval = self._game.get_drop_interval()
        self._auto_drop_timer.start(interval)

    def _on_auto_drop(self):
        """自动下落步进"""
        if self._game.state != GameState.PLAYING:
            return
        result = self._game.tick()

        # ★ 消行特效：如果有行被消除，暂停自动下落并播放动画
        cleared = result.get("cleared_rows", [])
        if cleared and not self._board_canvas.is_animating():
            self._auto_drop_timer.stop()
            self._start_btn.setEnabled(False)
            # 先同步消除前的棋盘状态（显示完整行用于闪烁）
            self._sync_board()
            self._status_bar.update_all(
                self._game.score, self._game.level, self._game.lines_cleared
            )
            self._board_canvas.start_clearing_animation(cleared)
            if result.get("level_up"):
                self._auto_drop_timer.setInterval(self._game.get_drop_interval())
            if result.get("game_over"):
                self._start_btn.setText("🔄 重玩")
            return

        self._sync_board()
        self._status_bar.update_all(
            self._game.score, self._game.level, self._game.lines_cleared
        )
        # 速度升级
        if result.get("level_up"):
            self._auto_drop_timer.setInterval(self._game.get_drop_interval())
        # 游戏结束
        if result.get("game_over"):
            self._auto_drop_timer.stop()
            self._start_btn.setText("🔄 重玩")

    def _on_left(self):
        self._game.move_left()
        self._sync_board()

    def _on_right(self):
        self._game.move_right()
        self._sync_board()

    def _on_rotate(self):
        self._game.rotate()
        self._sync_board()

    def _on_soft_drop(self):
        self._game.soft_drop()
        self._sync_board()
        self._status_bar.update_all(
            self._game.score, self._game.level, self._game.lines_cleared
        )

    def _on_hard_drop(self):
        result = self._game.hard_drop()
        cleared = result.get("cleared_rows", [])
        if cleared and not self._board_canvas.is_animating():
            self._auto_drop_timer.stop()
            self._start_btn.setEnabled(False)
            self._sync_board()
            self._status_bar.update_all(
                self._game.score, self._game.level, self._game.lines_cleared
            )
            self._board_canvas.start_clearing_animation(cleared)
        else:
            self._sync_board()
            self._status_bar.update_all(
                self._game.score, self._game.level, self._game.lines_cleared
            )

    def _on_pause(self):
        self._on_start_clicked()

    # ── 棋盘同步 ──

    def _on_clearing_done(self):
        """消行闪烁动画完成，恢复游戏"""
        self._start_btn.setEnabled(True)
        if self._game.state == GameState.PLAYING:
            self._start_auto_drop()
        # 闪烁后棋盘已被 lock_piece 更新，全量同步
        if self._game.state != GameState.GAME_OVER:
            self._sync_board()

    def _sync_board(self):
        """将游戏状态同步到画布"""
        board = self._game.get_board()
        current = self._game.get_current_piece()

        # 计算幽灵方块
        ghost_cells = []
        if current and self._game.state == GameState.PLAYING:
            ghost = self._calc_ghost(current, board)
            if ghost:
                ghost_cells = self._game._get_cells(ghost)

        # 注入当前方块的绝对坐标
        display_current = None
        if current:
            cells = self._game._get_current_cells()
            color = TETROMINOES.get(current["type"], {}).get("color", "#fff")
            display_current = {
                "type": current["type"],
                "rotation": current["rotation"],
                "x": current["x"],
                "y": current["y"],
                "cells": cells,
                "color": color,
            }

        self._board_canvas.set_game_data(board, display_current, ghost_cells)

        # 下一块预览
        next_piece = self._game.get_next_piece()
        self._preview_canvas.set_next_piece(next_piece or "")

        # 状态栏
        self._status_bar.update_all(
            self._game.score, self._game.level, self._game.lines_cleared
        )

    def _calc_ghost(self, current: dict, board) -> Optional[dict]:
        """计算幽灵方块位置（当前方块下落到底部的位置）"""
        ghost = {
            "type": current["type"],
            "rotation": current["rotation"],
            "x": current["x"],
            "y": current["y"],
        }
        shapes = TETROMINOES[current["type"]]["shapes"][current["rotation"]]
        width = self._game.width
        height = self._game.height

        def collides(p: dict) -> bool:
            for cx, cy in self._game._get_cells(p):
                if cx < 0 or cx >= width or cy >= height:
                    return True
                if cy >= 0 and board[cx][cy] is not None:
                    return True
            return False

        while not collides(ghost):
            ghost["y"] += 1
        ghost["y"] -= 1
        return ghost if ghost["y"] != current["y"] else None

    # ── 关闭 ──

    def _on_close(self):
        self._auto_drop_timer.stop()
        self.setVisible(False)
        self.closed.emit()

    def deleteLater(self):
        self._auto_drop_timer.stop()
        super().deleteLater()