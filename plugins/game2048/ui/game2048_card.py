# -*- coding: utf-8 -*-
"""2048 浮動卡片 — 在 DriFox 中直接玩经典 2048

功能：
- 4x4 网格，方向键滑动合并
- 计分与最高分记录
- 新游戏按钮
- 动画过渡效果
- 颜色按数字区分
- 跟随 DriFox 主题色

设计约束：
- 不导入 app.core 或 app.widgets 内部的任何模块
- 游戏逻辑通过 game_logic.Game2048 实现
"""

from typing import Callable, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QKeyEvent
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

from .game_logic import Game2048, Direction
from .widgets import TileButton, StatusBar


# ── 网格配置 ──
GRID_SIZE = 4
CELL_SIZE = 80
CELL_GAP = 10
GRID_MARGIN = 8


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


class Game2048Card(QWidget):
    """2048 浮動卡片"""

    closed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context_provider: Optional[Callable[[], dict]] = None

        # 游戏状态
        self._game: Optional[Game2048] = None
        self._tiles: list[list[TileButton]] = []
        self._animating = False
        self._prev_grid: list[list[int]] = []  # 移动前的网格快照

        self._setup_ui()
        self._new_game()

        # 设置焦点以接收键盘事件
        self.setFocusPolicy(Qt.StrongFocus)

    # ── 上下文注入 ──

    def set_context_provider(self, provider: Callable[[], dict]):
        """注入上下文提供函数（由 UIPluginRegistry 调用）"""
        self._context_provider = provider

    def show_card(self):
        """卡片显示时：用最新上下文刷新主题色"""
        self._apply_latest_theme()
        self.setVisible(True)
        self.setFocus()  # 获取键盘焦点

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

    # ── UI 搭建 ──

    def _setup_ui(self):
        self.setMinimumHeight(0)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("Game2048Card { background: transparent; }")

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

        self._title_label = StrongBodyLabel("2048", header)
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
        self._status_bar.new_game_clicked.connect(self._on_new_game_clicked)
        content_layout.addWidget(self._status_bar)

        # 游戏网格容器
        self._grid_container = QWidget(content)
        self._grid_container.setObjectName("gridContainer")
        
        # 网格背景色（经典 2048 底色）
        grid_bg_color = "#BBADA0"
        self._grid_container.setStyleSheet(f"""
            QWidget#gridContainer {{
                background: {grid_bg_color};
                border-radius: 8px;
            }}
        """)
        
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(CELL_GAP)
        self._grid_layout.setContentsMargins(GRID_MARGIN, GRID_MARGIN, GRID_MARGIN, GRID_MARGIN)
        
        # 创建所有格子（4x4）
        self._create_tiles()
        
        content_layout.addWidget(self._grid_container, 0, Qt.AlignCenter)

        # 提示标签
        self._hint_label = QLabel("使用 ↑ ↓ ← → 方向键移动", content)
        self._hint_label.setStyleSheet(f"""
            QLabel {{
                color: {_text_color(secondary=True)};
                font-size: 12px;
                background: transparent;
            }}
        """)
        content_layout.addWidget(self._hint_label, 0, Qt.AlignCenter)

        root.addWidget(content, 1)

    def _create_tiles(self):
        """创建所有格子按钮"""
        for x in range(GRID_SIZE):
            row = []
            for y in range(GRID_SIZE):
                tile = TileButton(x, y, CELL_SIZE, self._grid_container)
                tile.setEnabled(False)  # 不响应点击，只通过键盘控制
                self._grid_layout.addWidget(tile, y, x)
                row.append(tile)
            self._tiles.append(row)

    # ── 游戏逻辑 ──

    def _new_game(self):
        """开始新游戏"""
        self._game = Game2048()
        self._game.init()
        self._sync_grid(animate=True)
        self._update_status()
        # 清除游戏结束遮罩
        for child in self._grid_container.findChildren(QLabel):
            if child.property("overlay"):
                child.deleteLater()

    def _sync_grid(self, animate: bool = False):
        """同步游戏网格到 UI"""
        grid = self._game.get_grid()
        for x in range(GRID_SIZE):          # x = UI 列
            for y in range(GRID_SIZE):      # y = UI 行
                if x < len(self._tiles) and y < len(self._tiles[x]):
                    tile = self._tiles[x][y]
                    old_val = tile.get_value()
                    # ★ 修复：grid 是 [行][列]，UI 是 [列][行]
                    new_val = grid[y][x]

                    is_new = False
                    is_merged = False
                    if animate and new_val != 0:
                        if old_val == 0:
                            # 此位置之前空白 → 新生成的数字
                            is_new = True
                        elif new_val > old_val:
                            # 数值变大 → 合并产生
                            is_merged = True

                    tile.set_value(new_val, is_new=is_new, is_merged=is_merged)

    def _update_status(self):
        """更新状态栏"""
        self._status_bar.set_score(self._game.score)
        self._status_bar.set_best_score(self._game.best_score)

    def _on_new_game_clicked(self):
        """新游戏按钮点击"""
        self._new_game()

    # ── 键盘事件处理 ──

    def keyPressEvent(self, event: QKeyEvent):
        """处理键盘事件"""
        if self._game is None:
            return super().keyPressEvent(event)
        
        if self._animating:
            return

        direction_map = {
            Qt.Key_Up: Direction.UP,
            Qt.Key_Down: Direction.DOWN,
            Qt.Key_Left: Direction.LEFT,
            Qt.Key_Right: Direction.RIGHT,
        }

        direction = direction_map.get(event.key())
        if direction is None:
            return super().keyPressEvent(event)

        # 执行移动
        result = self._game.move(direction)
        
        if result["moved"]:
            self._animating = True
            self._sync_grid(animate=True)
            self._update_status()
            # 300ms 动画时间后解锁
            QTimer.singleShot(300, self._on_move_animation_complete)
        else:
            self._shake_grid()

        if result["game_over"]:
            QTimer.singleShot(350, self._show_game_over)
        elif result["won"]:
            QTimer.singleShot(350, self._show_win)

        super().keyPressEvent(event)

    def _on_move_animation_complete(self):
        """移动动画完成"""
        self._animating = False

    def _shake_grid(self):
        """无效移动抖动效果"""
        container = self._grid_container
        orig_pos = container.pos()
        def shake_frame(offset):
            container.move(orig_pos.x() + offset, orig_pos.y())
        def restore():
            container.move(orig_pos.x(), orig_pos.y())
        # 左-右-左 抖动
        for i, offset in enumerate([-4, 4, -2, 2, 0]):
            QTimer.singleShot(i * 30, lambda o=offset: shake_frame(o))
        QTimer.singleShot(150, restore)

    def _show_win(self):
        """显示胜利提示"""
        self._show_overlay("🎉 恭喜达到 2048！", "#EDC22E")

    def _show_game_over(self):
        """显示游戏结束"""
        self._show_overlay("💀 游戏结束", "#E94560")

    def _show_overlay(self, text: str, accent_color: str):
        """在网格上方显示遮罩层"""
        # 移除旧遮罩
        for child in self._grid_container.findChildren(QLabel):
            if child.property("overlay"):
                child.deleteLater()

        overlay = QLabel(text, self._grid_container)
        overlay.setProperty("overlay", True)
        overlay.setAlignment(Qt.AlignCenter)
        overlay.setStyleSheet(f"""
            QLabel {{
                background: rgba(0, 0, 0, 0.7);
                color: {accent_color};
                font-size: 22px;
                font-weight: bold;
                border-radius: 8px;
                padding: 20px;
            }}
        """)
        # 覆盖在网格容器上
        overlay.setGeometry(0, 0, self._grid_container.width(),
                            self._grid_container.height())
        overlay.raise_()
        overlay.show()

    # ── 关闭 ──

    def _on_close(self):
        self.setVisible(False)
        self.closed.emit()

    def deleteLater(self):
        super().deleteLater()