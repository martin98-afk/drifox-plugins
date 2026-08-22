# -*- coding: utf-8 -*-
"""中国象棋浮动卡片 — 在 DriFox 中对弈大模型

游戏循环：
1. 玩家执红（先手），点击棋子选中 → 点击目标落子
2. 检查胜负（将死/困毙）→ 未结束则轮到 AI
3. AI 执黑：ai_engine.start_ai_move() 单轮调大模型 → 拿到走法后走子
4. 循环直到分出胜负

设计约束：
- 不导入 app.core 内部模块
- 游戏逻辑通过 ui/game_logic 模块（纯 Python）
- AI 调用通过 ui/ai_engine（读 main_widget._valid_configs 拿模型配置）
"""

from typing import Any, Callable, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from loguru import logger

from .game_logic import (
    BLACK,
    RED,
    ROWS,
    COLS,
    coord_to_str,
    gen_legal_moves,
    initial_board,
    make_move,
    side_of,
)
from .ai_engine import start_ai_move
from .widgets import ChessBoardView


class ChessCard(QWidget):
    """中国象棋浮动卡片"""

    closed = pyqtSignal()

    # 文本回退色（无主题上下文时使用）
    _FG = "rgba(0,0,0,0.85)"
    _FG_DIM = "rgba(0,0,0,0.5)"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context_provider: Optional[Callable[[], dict]] = None

        # 游戏状态
        self._board = initial_board()
        self._side_to_move = RED
        self._selected: Optional[tuple] = None
        self._game_over = False
        self._winner: Optional[str] = None  # RED / BLACK
        self._last_move: Optional[tuple] = None
        self._history: list = []  # [(move, side), ...]
        self._ai_task: Optional[Any] = None  # QRunnable 占位（新对局时用以丢弃结果）

        self._setup_ui()
        self._refresh_status()
        self._board_view.set_pieces(self._board)
        self._board_view.clicked.connect(self._on_board_click)

    # ── 上下文注入（FloatingCard 协议） ──

    def set_context_provider(self, provider: Callable[[], dict]):
        self._context_provider = provider

    def show_card(self):
        """卡片显示时拉取主题（暂未自定义样式）"""
        self.setVisible(True)

    # ── UI 搭建 ──

    def _setup_ui(self):
        self.setMinimumWidth(580)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # 顶部状态栏
        top = QHBoxLayout()
        self._status_label = QLabel("轮到：红方（你）")
        f = QFont("Microsoft YaHei", 12)
        f.setBold(True)
        self._status_label.setFont(f)
        top.addWidget(self._status_label)
        top.addStretch(1)
        self._new_game_btn = QPushButton("新对局")
        self._new_game_btn.clicked.connect(self._new_game)
        self._new_game_btn.setFixedHeight(28)
        top.addWidget(self._new_game_btn)
        root.addLayout(top)

        # 棋盘（居中）
        self._board_view = ChessBoardView(cell=52, parent=self)
        wrap = QHBoxLayout()
        wrap.addStretch(1)
        wrap.addWidget(self._board_view)
        wrap.addStretch(1)
        root.addLayout(wrap)

        # 底部提示
        self._hint_label = QLabel("点击己方棋子选中 → 点击目标格落子")
        self._hint_label.setAlignment(Qt.AlignCenter)
        self._hint_label.setStyleSheet(f"color: {self._FG_DIM}; font-size: 11px;")
        root.addWidget(self._hint_label)
        root.addStretch(1)

    # ── 状态显示 ──

    def _refresh_status(self):
        if self._game_over:
            if self._winner == RED:
                self._status_label.setText("🏆 红方胜利！点击「新对局」重开")
            elif self._winner == BLACK:
                self._status_label.setText("🏆 黑方胜利！点击「新对局」重开")
            else:
                self._status_label.setText("对局结束")
        else:
            side_cn = "红方（你）" if self._side_to_move == RED else "黑方（大模型）"
            self._status_label.setText(f"轮到：{side_cn}")

    # ── 新对局 ──

    def _stop_ai_worker(self):
        """停止 AI 任务（新对局 / 关闭卡片时）

        QRunnable 无法中途 kill HTTP，仅置 None 占位；后台任务返回时
        通过 _on_ai_done 检查 self._game_over / self._side_to_move 决定是否落子。
        """
        self._ai_task = None

    def _new_game(self):
        self._stop_ai_worker()
        self._board = initial_board()
        self._side_to_move = RED
        self._selected = None
        self._game_over = False
        self._winner = None
        self._last_move = None
        self._history = []
        self._board_view.set_pieces(self._board)
        self._board_view.set_selected(None)
        self._board_view.set_legal_targets([])
        self._board_view.set_last_move(None)
        self._hint_label.setText("点击己方棋子选中 → 点击目标格落子")
        self._refresh_status()

    # ── 点击处理 ──

    def _on_board_click(self, c: int, r: int):
        if self._game_over or self._side_to_move != RED:
            return
        piece = self._board[r][c]
        if self._selected is None:
            if piece != "." and side_of(piece) == RED:
                self._select_piece(c, r)
            return
        c1, r1 = self._selected
        if (c, r) == (c1, r1):
            self._select_piece(None)
            return
        legal = gen_legal_moves(self._board, RED)
        move = (c1, r1, c, r)
        if move in legal:
            self._apply_move(move)
        elif piece != "." and side_of(piece) == RED:
            # 切换选中
            self._select_piece(c, r)
        else:
            self._select_piece(None)

    def _select_piece(self, c=None, r=None):
        """选中 (c, r) 处的棋子；传 None 表示取消选中。"""
        pos = None if c is None else (c, r)
        self._selected = pos
        if pos is None:
            self._board_view.set_selected(None)
            self._board_view.set_legal_targets([])
            return
        self._board_view.set_selected(pos)
        targets = [(nc, nr) for (fc, fr, nc, nr) in gen_legal_moves(self._board, RED) if (fc, fr) == (c, r)]
        self._board_view.set_legal_targets(targets)

    # ── 走子 ──

    def _apply_move(self, move):
        from .game_logic import is_checkmate, is_stalemate

        side = self._side_to_move
        self._board = make_move(self._board, move)
        self._last_move = move
        self._history.append((move, side))
        self._board_view.set_pieces(self._board)
        self._board_view.set_last_move(move)
        self._selected = None
        self._board_view.set_selected(None)
        self._board_view.set_legal_targets([])

        next_side = BLACK if side == RED else RED
        self._side_to_move = next_side

        # 检查胜负（对 next_side）
        if is_checkmate(self._board, next_side) or is_stalemate(self._board, next_side):
            self._game_over = True
            self._winner = side  # 刚走子的一方胜
            self._refresh_status()
            self._hint_label.setText("对局结束。点击「新对局」重开。")
            return

        self._refresh_status()

        if self._side_to_move == BLACK:
            self._start_ai_move()

    # ── AI ──

    def _start_ai_move(self):
        self._status_label.setText("轮到：黑方（大模型）— 思考中…")
        self._hint_label.setText("🤖 大模型思考中…")
        ok = start_ai_move(self)
        if not ok:
            self._hint_label.setText("⚠️ 模型配置或上下文不可用，无法调用大模型")
            self._game_over = True
            self._winner = RED  # 玩家胜（AI 无法启动）
            self._refresh_status()

    def _on_ai_done(self, move, source):
        self._ai_task = None
        # 用户已开新对局/关闭卡片 → 丢弃本次 AI 结果
        if self._game_over or self._side_to_move != BLACK:
            return
        if move is None:
            self._hint_label.setText("AI 未能走子，点击「新对局」重开")
            self._game_over = True
            self._winner = RED  # 玩家胜（AI 弃权）
            self._refresh_status()
            return
        src_cn = {"llm": "LLM", "fallback": "兜底", "error": "出错"}.get(source, source)
        c1, r1, c2, r2 = move
        self._hint_label.setText(f"AI 走法：{coord_to_str(c1, r1)} → {coord_to_str(c2, r2)}（{src_cn}）")
        self._apply_move(move)

    def _on_ai_failed(self, reason: str):
        # 仅记录，不覆盖 done 的 UI 行为
        logger.warning(f"[chinese-chess] AI failed: {reason}")
        self._hint_label.setText(f"⚠️ {reason}")

    # ── 关闭清理 ──

    def _on_close(self):
        self._stop_ai_worker()
        self.setVisible(False)
        self.closed.emit()
