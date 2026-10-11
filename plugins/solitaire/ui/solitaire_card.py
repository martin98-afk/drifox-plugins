# -*- coding: utf-8 -*-
"""接龙（Klondike）浮动卡片 — 在 DriFox 中直接玩经典接龙

功能：
- 经典 7 列 + 4 收牌堆 + 翻一张牌堆，绿桌布配色
- 拖拽移动（序列整体跟拖）、双击自动上收牌堆、点击牌堆翻牌
- 步数与用时统计
- 跟随 DriFox 主题（标题/状态文字色）

设计约束：
- 不导入 app.core 或 app.widgets 内部的任何模块
- 游戏规则全部在 game_logic.Board，本文件只做交互与渲染
"""

from typing import Callable, List, Optional

from PyQt5.QtCore import QElapsedTimer, QPoint, QRect, Qt, QTimer, \
    pyqtSignal
from PyQt5.QtGui import QPainter, QPixmap
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import FluentIcon, IconWidget, StrongBodyLabel, \
    TransparentToolButton, isDarkTheme
from loguru import logger

from .game_logic import Board, SUITS
from .widgets import CARD_H, CARD_W, CardWidget, DropZone

_DEBUG = "[SOL-DBG]"

# ── 桌面布局常数 ──
MARGIN = 12
GAP = 8
BOARD_W = MARGIN + 7 * CARD_W + 6 * GAP + MARGIN   # 520
TOP_Y = MARGIN
TAB_Y = TOP_Y + CARD_H + 12
TAB_H = 348
BOARD_H = TAB_Y + TAB_H

STOCK_X = MARGIN
WASTE_X = MARGIN + CARD_W + GAP
FOUND_X0 = BOARD_W - MARGIN - 4 * CARD_W - 3 * GAP
TAB_STEP_UP = 26    # 明牌间距
TAB_STEP_DOWN = 14  # 暗牌间距
TAB_STEP_MIN = 8
DRAG_THRESHOLD = 8


# ── 主题色辅助（同 game2048）──

def _text_color(secondary: bool = False) -> str:
    if isDarkTheme():
        return "rgba(255,255,255,0.55)" if secondary else "rgba(255,255,255,0.9)"
    return "rgba(0,0,0,0.45)" if secondary else "rgba(0,0,0,0.85)"


def _ctx_text_color(ctx: dict, secondary: bool = False) -> str:
    colors = ctx.get("colors", {})
    key = "text_secondary" if secondary else "text_primary"
    val = colors.get(key, "")
    return val if val else _text_color(secondary)


class _HelpOverlay(QLabel):
    """玩法说明遮罩：点击任意处关闭"""

    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class SolitaireCard(QWidget):
    """接龙浮动卡片：UI 渲染 + 拖拽控制器"""

    closed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context_provider: Optional[Callable[[], dict]] = None
        self._board = Board()

        # widget 管理
        self._card_widgets: List[CardWidget] = []
        self._drop_zones: List[DropZone] = []

        # 拖拽状态
        self._drag: Optional[dict] = None
        self._ghost: Optional[QLabel] = None
        self._press_gpos = None

        # 计时
        self._elapsed = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._update_time_label)
        self._finished = False

        self._setup_ui()
        self._new_game()
        logger.info(f"{_DEBUG} v0.1.1 instantiated id={id(self):x}")

    # ── 上下文注入（UIPluginRegistry 契约）──

    def set_context_provider(self, provider: Callable[[], dict]):
        self._context_provider = provider

    def show_card(self):
        """卡片显示时：刷新主题色并恢复计时"""
        self._apply_latest_theme()
        self.setVisible(True)
        if not self._finished:
            self._timer.start()

    def _apply_latest_theme(self):
        if self._context_provider is None:
            return
        try:
            ctx = self._context_provider()
        except Exception:
            return
        tc = _ctx_text_color(ctx)
        self._title_label.setStyleSheet(
            f"color: {tc}; background: transparent;")

    # ── UI 搭建 ──

    def _setup_ui(self):
        self.setMinimumHeight(0)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("SolitaireCard { background: transparent; }")

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

        self._title_label = StrongBodyLabel("接龙 v0.1.1", header)
        self._title_label.setStyleSheet(
            f"color: {_text_color()}; background: transparent;")
        hly.addWidget(self._title_label)
        hly.addStretch(1)

        help_btn = TransparentToolButton(FluentIcon.INFO, header)
        help_btn.setFixedSize(24, 24)
        help_btn.setToolTip("玩法说明")
        help_btn.clicked.connect(self._show_help)
        hly.addWidget(help_btn)

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

        # ── 内容区 ──
        content = QWidget(self)
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 8, 0, 12)
        content_layout.setSpacing(8)
        content_layout.setAlignment(Qt.AlignHCenter)

        # 牌桌（绿桌布，绝对定位）
        self._board_area = QWidget(content)
        self._board_area.setFixedSize(BOARD_W, BOARD_H)
        self._board_area.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1E6B45, stop:1 #17573A);
                border-radius: 10px;
            }
        """)
        self._build_drop_zones()
        content_layout.addWidget(self._board_area, 0, Qt.AlignHCenter)

        # 状态栏
        status = QWidget(content)
        status.setStyleSheet("background: transparent;")
        sly = QHBoxLayout(status)
        sly.setContentsMargins(16, 0, 16, 0)
        sly.setSpacing(12)

        self._moves_label = QLabel("步数 0", status)
        self._moves_label.setStyleSheet(
            f"color: {_text_color(secondary=True)}; font-size: 12px;")
        sly.addWidget(self._moves_label)

        self._time_label = QLabel("时间 00:00", status)
        self._time_label.setStyleSheet(
            f"color: {_text_color(secondary=True)}; font-size: 12px;")
        sly.addWidget(self._time_label)

        sly.addStretch(1)

        self._new_game_btn = QPushButton("新游戏", status)
        self._new_game_btn.setCursor(Qt.PointingHandCursor)
        self._new_game_btn.setStyleSheet("""
            QPushButton {
                background: #2E7D52; color: #FFFFFF; border: none;
                border-radius: 6px; padding: 4px 14px;
                font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background: #359060; }
            QPushButton:pressed { background: #276C47; }
        """)
        self._new_game_btn.clicked.connect(self._new_game)
        sly.addWidget(self._new_game_btn)

        content_layout.addWidget(status, 0, Qt.AlignHCenter)
        root.addWidget(content, 1)

    def _build_drop_zones(self):
        """常驻占位框：牌堆 / 废牌 / 4 收牌堆 / 7 列"""
        self._drop_zones = []
        # stock（点击处理在 _refresh 里对占位框重绑定）
        self._stock_zone = DropZone("stock", on_click=self._on_stock_clicked,
                                    parent=self._board_area)
        self._stock_zone.move(STOCK_X, TOP_Y)
        self._drop_zones.append(self._stock_zone)

        self._drop_zones.append(
            DropZone("waste", parent=self._board_area))
        self._drop_zones[-1].move(WASTE_X, TOP_Y)

        self._foundation_rects = {}
        for i, suit in enumerate(SUITS):
            x = FOUND_X0 + i * (CARD_W + GAP)
            zone = DropZone("foundation", suit=suit, parent=self._board_area)
            zone.move(x, TOP_Y)
            self._drop_zones.append(zone)
            self._foundation_rects[suit] = QRect(x, TOP_Y, CARD_W, CARD_H)

        self._tab_bands = []
        for col in range(7):
            x = MARGIN + col * (CARD_W + GAP)
            zone = DropZone("col", parent=self._board_area)
            zone.move(x, TAB_Y)
            zone.lower()  # 列占位框垫底
            self._drop_zones.append(zone)
            self._tab_bands.append(
                QRect(x, TAB_Y, CARD_W, TAB_H))

    # ── 渲染刷新（全量重建，52 张成本可忽略）──

    def _refresh(self):
        for w in self._card_widgets:
            w.hide()
            w.deleteLater()
        self._card_widgets = []
        board = self._board

        # stock 顶张（牌背），堆空时露出占位框
        if board.stock_count() > 0:
            self._add_card(("stock",), 0,
                           board.stock_cards()[-1], False,
                           STOCK_X, TOP_Y)

        # waste 顶张
        wt = board.waste_top()
        if wt is not None:
            self._add_card(("waste",), 0, wt, True, WASTE_X, TOP_Y)

        # foundation 顶张
        for i, suit in enumerate(SUITS):
            top = board.foundation_top(suit)
            if top is not None:
                x = FOUND_X0 + i * (CARD_W + GAP)
                self._add_card(("foundation", suit), 0, top, True,
                               x, TOP_Y)

        # tableau：顺序创建，列底牌最后 z 序最高，完整显示；
        # 其上每张只露出顶部 step 条（rank 角标可见），经典接龙阶梯视觉
        for col in range(7):
            pile = board.tableau_col(col)
            steps = self._col_offsets(pile)
            x = MARGIN + col * (CARD_W + GAP)
            for i, tc in enumerate(pile):
                y = TAB_Y + steps[i]
                self._add_card(("tableau", col), i, tc.card,
                               tc.face_up, x, y)

        self._moves_label.setText(f"步数 {board.moves}")
        # [SOL-DBG] 临时诊断：每列牌数 / widget 数 / 抽样列的 y 与可见性
        col_info = [len(board.tableau_col(c)) for c in range(7)]
        sample = None
        for c in range(7):
            ws = [w for w in self._card_widgets if w.pile == ("tableau", c)]
            if len(ws) > 2:
                ws.sort(key=lambda w: w.idx)
                sample = [(w.idx, w.y(), w.isVisible(), w.isHidden())
                          for w in ws]
                break
        logger.info(f"{_DEBUG} refresh cols={col_info} "
                    f"widgets={len(self._card_widgets)} sample={sample}")
        if board.is_won and not self._finished:
            self._finished = True
            self._timer.stop()
            QTimer.singleShot(200, self._show_win)

    def _add_card(self, pile: tuple, idx: int, card, face_up: bool,
                  x: int, y: int) -> CardWidget:
        cw = CardWidget(pile, idx, face_up, self, self._board_area)
        cw.set_card(card)
        cw.move(x, y)
        cw.show()
        self._card_widgets.append(cw)
        return cw

    @staticmethod
    def _col_offsets(pile) -> List[int]:
        """列内每张牌相对 TAB_Y 的偏移；过长时压缩间距"""
        n = len(pile)
        if n == 0:
            return []
        steps = [0]
        for i in range(n - 1):
            steps.append(TAB_STEP_DOWN if not pile[i].face_up
                         else TAB_STEP_UP)
        total = steps[-1] + CARD_H
        if total > TAB_H and total > CARD_H:
            scale = (TAB_H - CARD_H) / (total - CARD_H)
            for i in range(1, n):
                steps[i] = max(TAB_STEP_MIN, int(steps[i] * scale))
        return steps

    # ── 事件：牌堆 / 双击 ──

    def _on_stock_clicked(self):
        if self._drag is not None:
            return
        self._board.draw()
        self._refresh()

    def on_card_double_click(self, cw: CardWidget):
        if self._drag is not None or not cw.is_face_up:
            return
        src = self._source_of(cw)
        if src is None:
            return
        if self._board.move_to_foundation(src)["ok"]:
            self._refresh()

    # ── 事件：拖拽 ──

    def on_card_pressed(self, cw: CardWidget, global_pos):
        """按下即响应：牌堆牌背点击翻牌，同时记录按下坐标供拖拽阈值判定"""
        self._press_gpos = global_pos
        if cw.pile == ("stock",):
            self._on_stock_clicked()

    def on_card_drag_move(self, cw: CardWidget, global_pos):
        if self._drag is None:
            self._maybe_start_drag(cw, global_pos)
            return
        pos = self._board_area.mapFromGlobal(global_pos)
        self._ghost.move(pos + self._drag["offset"])

    def _maybe_start_drag(self, cw: CardWidget, global_pos):
        if not cw.is_face_up or cw.pile == ("stock",):
            return
        # 阈值：按下后移动超过 DRAG_THRESHOLD 才算拖拽，避免点击误触
        if self._press_gpos is None:
            return
        if (global_pos - self._press_gpos).manhattanLength() < DRAG_THRESHOLD:
            return
        src = self._source_of(cw)
        if src is None:
            return
        cards = self._board.peek_source(src)
        if not cards:
            return

        # 序列对应 widget 与拖影内间距
        seq_widgets, step = self._seq_widgets_of(cw)
        total_h = CARD_H + step * (len(cards) - 1)
        pm = QPixmap(CARD_W, total_h)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(0.85)
        for i, w in enumerate(seq_widgets):
            w.render(p, QPoint(0, i * step))
        p.end()

        # 拖影顶左相对鼠标的偏移
        mouse = self._board_area.mapFromGlobal(global_pos)
        tl = cw.mapTo(self._board_area, QPoint(0, 0))

        ghost = QLabel(self._board_area)
        ghost.setPixmap(pm)
        ghost.move(tl)
        ghost.show()
        ghost.raise_()

        # 注意：不 hide 原牌——hide 会释放 Qt 隐式鼠标 grab，
        # 后续 move/release 不再投递，拖拽会卡死。原牌留在原地。
        self._ghost = ghost
        self._drag = {
            "src": src,
            "cards": cards,
            "seq": seq_widgets,
            "offset": tl - mouse,
        }
        logger.info(f"{_DEBUG} drag start src={src} n={len(cards)}")

    def on_card_release(self, cw: CardWidget, global_pos):
        if self._drag is None:
            return
        drag, self._drag = self._drag, None
        ghost, self._ghost = self._ghost, None

        target = self._hit_target(global_pos)
        moved = False
        if target is not None:
            if target[0] == "foundation" and len(drag["cards"]) == 1:
                moved = self._board.move_to_foundation(drag["src"])["ok"]
            elif target[0] == "tableau":
                moved = self._board.move_to_tableau(
                    drag["src"], target[1])["ok"]

        ghost.deleteLater()
        if moved:
            self._refresh()
        # 未移动：原牌一直在原地，无需恢复
        logger.info(f"{_DEBUG} release target={target} moved={moved}")

    def _seq_widgets_of(self, cw: CardWidget):
        """返回拖拽序列对应的 widget 列表与拖影内间距"""
        if cw.pile[0] == "waste":
            return [cw], 0
        _, col = cw.pile[0], cw.pile[1]
        pile = self._board.tableau_col(col)
        offsets = self._col_offsets(pile)
        seq = [w for w in self._card_widgets
               if w.pile == cw.pile and w.idx >= cw.idx]
        seq.sort(key=lambda w: w.idx)
        step = offsets[cw.idx] if cw.idx < len(offsets) else TAB_STEP_UP
        return seq, step

    def _source_of(self, cw: CardWidget):
        if cw.pile[0] == "tableau":
            return ("tableau", cw.pile[1], cw.idx)
        if cw.pile[0] == "waste":
            return ("waste",)
        return None

    def _hit_target(self, global_pos):
        pos = self._board_area.mapFromGlobal(global_pos)
        for suit, rect in self._foundation_rects.items():
            if rect.adjusted(-6, -6, 6, 6).contains(pos):
                return ("foundation", suit)
        for col, band in enumerate(self._tab_bands):
            if band.contains(pos):
                return ("tableau", col)
        return None

    # ── 玩法说明遮罩 ──

    def _clear_help(self):
        for w in self._board_area.findChildren(_HelpOverlay):
            w.deleteLater()

    def _show_help(self):
        self._clear_help()
        overlay = _HelpOverlay(self._board_area)
        overlay.setText(
            "<b>玩法说明</b><br><br>"
            "• 按住明牌拖到目标列：红黑交替、点数递减，"
            "序列可整体拖动；空列只能放 K<br>"
            "• 双击单张明牌：自动送上对应花色的收牌堆<br>"
            "• 点左上牌堆翻牌；翻完后点空牌堆把废牌重新洗回<br>"
            "• 四个收牌堆按花色 A → K 收齐即通关<br><br>"
            "<i>点击任意处关闭</i>"
        )
        overlay.setGeometry(0, 0, BOARD_W, BOARD_H)
        overlay.setStyleSheet("""
            QLabel {
                background: rgba(0, 0, 0, 0.78);
                color: rgba(255, 255, 255, 0.92);
                font-size: 13px;
                border-radius: 10px;
                padding: 28px 40px;
            }
        """)
        overlay.clicked.connect(overlay.deleteLater)
        overlay.show()
        overlay.raise_()

    # ── 游戏控制 ──

    def _new_game(self):
        self._board.new_game()
        self._finished = False
        self._elapsed.start()
        self._timer.start()
        self._update_time_label()
        self._clear_win_overlay()
        self._refresh()

    def _update_time_label(self):
        secs = int(self._elapsed.elapsed() / 1000)
        self._time_label.setText(f"时间 {secs // 60:02d}:{secs % 60:02d}")

    def _show_win(self):
        for child in self._board_area.findChildren(QLabel):
            if child.property("overlay"):
                child.deleteLater()
        overlay = QLabel("🎉 通关！用时见下方", self._board_area)
        overlay.setProperty("overlay", True)
        overlay.setAlignment(Qt.AlignCenter)
        overlay.setGeometry(0, 0, BOARD_W, BOARD_H)
        overlay.setStyleSheet("""
            QLabel {
                background: rgba(0, 0, 0, 0.65);
                color: #FFD54F;
                font-size: 24px;
                font-weight: bold;
                border-radius: 10px;
            }
        """)
        overlay.raise_()
        overlay.show()

    def _clear_win_overlay(self):
        for child in self._board_area.findChildren(QLabel):
            if child.property("overlay"):
                child.deleteLater()

    # ── 关闭 ──

    def _on_close(self):
        self._timer.stop()
        self.setVisible(False)
        self.closed.emit()

    def deleteLater(self):
        self._timer.stop()
        super().deleteLater()
