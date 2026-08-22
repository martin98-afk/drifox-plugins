# -*- coding: utf-8 -*-
"""走子动效测试（#6）

覆盖：
- animate_last_move 启动后 _animating=True + timer 存活
- 3 轮（30 帧）后 _animating=False（立即推进 frame 模拟 1.5s 流逝）
- _draw_path_arrow 仅在车/炮时调用
- compute_attack_path 各种情形（直线/不共线/炮跳棋架）
- _captured_piece 在 _apply_move 吃子时被记录
- 状态机 guard：动效中点击被忽略
- QPropertyAnimation 创建被吃棋子淡出副本
- _GhostPieceLabel 视觉对照
"""

import sys
import os
import unittest
import types
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# QApplication 必须先存在
from PyQt5.QtWidgets import QApplication, QLabel
from PyQt5.QtCore import QTimer, QPropertyAnimation

_app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841

from ui import theme
from ui.game_logic import (
    RED, BLACK, ROWS, COLS, initial_board, make_move, side_of,
)
from ui.widgets import (
    ChessBoardView, PieceLabel, compute_attack_path, _GhostPieceLabel,
)


def _make_empty_board_with_king(side=RED):
    """构造一个空棋盘，仅留己方帅，避免被将死陷阱。"""
    board = [["." for _ in range(COLS)] for _ in range(ROWS)]
    if side == RED:
        board[9][4] = "K"
    else:
        board[0][4] = "k"
    return board


def _make_attacking_position():
    """构造一个车能直线吃子的局面（红方车直下吃黑车）。"""
    board = _make_empty_board_with_king(RED)
    board[9][0] = "R"  # 红车
    board[0][0] = "r"  # 黑车（红方直下的目的地）
    return board


class TestComputeAttackPath(unittest.TestCase):
    """compute_attack_path 单元测试"""

    def test_rook_horizontal(self):
        board = _make_empty_board_with_king(RED)
        board[5][0] = "R"
        # (0,5) → (8,5)：8 个中间格
        path = compute_attack_path((0, 5), (8, 5), board, "R")
        self.assertEqual(len(path), 7)
        self.assertEqual(path[0], (1, 5))
        self.assertEqual(path[-1], (7, 5))

    def test_rook_vertical(self):
        board = _make_empty_board_with_king(RED)
        board[9][0] = "R"
        # (0,9) → (0,0)：9 个中间格
        path = compute_attack_path((0, 9), (0, 0), board, "R")
        self.assertEqual(len(path), 8)
        self.assertEqual(path[0], (0, 8))
        self.assertEqual(path[-1], (0, 1))

    def test_non_collinear_returns_empty(self):
        board = _make_empty_board_with_king(RED)
        # (0,0) → (4,4) 不共线
        path = compute_attack_path((0, 0), (4, 4), board, "R")
        self.assertEqual(path, [])

    def test_cannon_jump_screen_skips_pre_screen(self):
        """炮跳棋架：只显示棋架之后的格子"""
        board = _make_empty_board_with_king(RED)
        board[9][0] = "C"  # 红炮 (0,9)
        board[5][0] = "p"  # 棋架（卒）(0,5)
        board[0][0] = "r"  # 黑车（目标）(0,0)
        # 红炮隔 (0,5) 棋架吃 (0,0)
        # 期望：屏幕 = (0,5)，跳到 (0,0) 之前的中转格只剩 [(0,4),(0,3),(0,2),(0,1)]
        path = compute_attack_path((0, 9), (0, 0), board, "C")
        # 棋架 (0,5) 之后 → (0,4),(0,3),(0,2),(0,1)
        self.assertEqual(path, [(0, 4), (0, 3), (0, 2), (0, 1)])

    def test_cannon_no_screen_returns_empty(self):
        board = _make_empty_board_with_king(RED)
        board[9][0] = "C"
        board[5][0] = "."  # 无棋架
        board[0][0] = "r"
        path = compute_attack_path((0, 9), (0, 0), board, "C")
        self.assertEqual(path, [])

    def test_knight_returns_empty(self):
        """马不是直线移动，返回空列表"""
        board = _make_empty_board_with_king(RED)
        board[9][1] = "N"
        path = compute_attack_path((1, 9), (0, 7), board, "N")
        self.assertEqual(path, [])


class TestAnimateLastMove(unittest.TestCase):
    """ChessBoardView.animate_last_move 单元测试"""

    def setUp(self):
        self.view = ChessBoardView(cell=52)

    def test_animate_sets_animating_true(self):
        self.assertFalse(self.view._animating)
        self.view.animate_last_move((0, 9), (0, 5), piece_type="R")
        self.assertTrue(self.view._animating)
        self.assertTrue(self.view._anim_timer.isActive())

    def test_animate_saves_from_to(self):
        self.view.animate_last_move((1, 9), (1, 7), piece_type="N")
        self.assertEqual(self.view._anim_from, (1, 9))
        self.assertEqual(self.view._anim_to, (1, 7))

    def test_animate_with_linear_piece_computes_path(self):
        board = _make_attacking_position()
        self.view.set_board_snapshot(board)
        self.view.animate_last_move((0, 9), (0, 0), piece_type="R")
        # 红车直下吃黑车 → 路径 8 格
        self.assertEqual(len(self.view._anim_path), 8)

    def test_animate_with_knight_no_path(self):
        self.view.animate_last_move((1, 9), (2, 7), piece_type="N")
        # 马走 L 形 → 不画路径
        self.assertEqual(self.view._anim_path, [])

    def test_animate_stops_after_max_frames(self):
        self.view.animate_last_move((0, 9), (0, 0), piece_type="R")
        # 模拟 30 次 tick（达到 ANIM_PULSE_FRAMES）
        for _ in range(self.view.ANIM_PULSE_FRAMES):
            self.view._on_anim_tick()
        # 动效结束
        self.assertFalse(self.view._animating)
        self.assertIsNone(self.view._anim_timer)

    def test_animate_partial_frames_keeps_active(self):
        self.view.animate_last_move((0, 9), (0, 5), piece_type="R")
        # 推进 5 帧（远小于 30）
        for _ in range(5):
            self.view._on_anim_tick()
        self.assertTrue(self.view._animating)
        self.assertEqual(self.view._anim_frame, 5)

    def test_animate_invalidates_old_timer(self):
        """连续启动两次动效：旧 timer 应被停止"""
        self.view.animate_last_move((0, 9), (0, 5), piece_type="R")
        old_timer = self.view._anim_timer
        self.view.animate_last_move((0, 9), (0, 4), piece_type="R")
        # 旧 timer 应停止（不是同一对象）
        self.assertFalse(old_timer.isActive())
        self.assertNotEqual(id(self.view._anim_timer), id(old_timer))


class TestCapturedPieceFade(unittest.TestCase):
    """被吃棋子淡出动效测试"""

    def setUp(self):
        self.view = ChessBoardView(cell=52)

    def test_animate_captured_creates_ghost_widget(self):
        """有被吃棋子时创建 _GhostPieceLabel"""
        # 统计现有的 QLabel 子项（不含自己）
        before = sum(1 for _ in self.view.findChildren(QLabel))
        self.view.animate_last_move((0, 9), (0, 0), piece_type="R",
                                     captured_piece=("r", 0, 0))
        # 应多一个 _GhostPieceLabel 子项
        ghosts = [c for c in self.view.findChildren(QLabel)
                  if isinstance(c, _GhostPieceLabel)]
        self.assertEqual(len(ghosts), 1)
        # 文字应是中文"车"
        self.assertEqual(ghosts[0].text(), "车")

    def test_no_captured_no_ghost(self):
        """无被吃 → 不创建 ghost"""
        self.view.animate_last_move((0, 9), (0, 5), piece_type="R",
                                     captured_piece=None)
        ghosts = [c for c in self.view.findChildren(QLabel)
                  if isinstance(c, _GhostPieceLabel)]
        self.assertEqual(len(ghosts), 0)

    def test_ghost_has_animation_attached(self):
        """ghost 应有 QPropertyAnimation（_anim 属性）"""
        self.view.animate_last_move((0, 9), (0, 0), piece_type="R",
                                     captured_piece=("r", 0, 0))
        ghosts = [c for c in self.view.findChildren(QLabel)
                  if isinstance(c, _GhostPieceLabel)]
        self.assertTrue(hasattr(ghosts[0], "_anim"))
        self.assertIsInstance(ghosts[0]._anim, QPropertyAnimation)


class TestGhostPieceLabelVisual(unittest.TestCase):
    """_GhostPieceLabel 视觉对照（不依赖 QApplication rendering）"""

    def setUp(self):
        # 必须给个真正的 QWidget 作为 parent（不能用 QApplication 实例）
        self.view = ChessBoardView(cell=52)

    def test_red_ghost_styled(self):
        ghost = _GhostPieceLabel("R", 40, self.view)
        self.assertEqual(ghost._side, "red")
        self.assertIn("#c62828", ghost.styleSheet() or "")
        self.assertEqual(ghost.text(), "车")

    def test_black_ghost_styled(self):
        ghost = _GhostPieceLabel("r", 40, self.view)
        self.assertEqual(ghost._side, "black")
        self.assertEqual(ghost.text(), "车")

    def test_ghost_empty_piece_returns_early(self):
        ghost = _GhostPieceLabel(".", 40, self.view)
        self.assertEqual(ghost.text(), "")

    def test_opacity_property(self):
        """opacity 可读写"""
        ghost = _GhostPieceLabel("R", 40, self.view)
        ghost._set_opacity(0.5)
        self.assertEqual(ghost._get_opacity(), 0.5)

    def test_opacity_backed_by_graphics_opacity_effect(self):
        """opacity 属性应走 QGraphicsOpacityEffect（修复 setWindowOpacity 对子部件无效）"""
        from PyQt5.QtWidgets import QGraphicsOpacityEffect
        ghost = _GhostPieceLabel("R", 40, self.view)
        self.assertIsInstance(ghost._ghost_effect, QGraphicsOpacityEffect)
        ghost._set_opacity(0.3)
        self.assertEqual(ghost._get_opacity(), 0.3)
        self.assertAlmostEqual(ghost._ghost_effect.opacity(), 0.3)


class TestThemeNewColors(unittest.TestCase):
    """theme.py 的 #6 新色值存在"""

    def test_pulse_colors(self):
        self.assertEqual(theme.LAST_MOVE_FROM_HIGHLIGHT, "rgba(102, 152, 255, 0.7)")
        self.assertEqual(theme.LAST_MOVE_TO_HIGHLIGHT, "rgba(212, 175, 55, 0.7)")
        self.assertEqual(theme.CAPTURED_PIECE_BG, "#fff4d6")
        self.assertEqual(theme.PATH_ARROW_COLOR, "rgba(212, 175, 55, 0.6)")


# ═════════════════════════════════════════════════════════════════
# ChessCard 状态机测试（#6 guard）
# ═════════════════════════════════════════════════════════════════

class TestAnimatingGuard(unittest.TestCase):
    """棋盘动效期间 _on_board_click / _apply_move 应被 guard 拦截"""

    def setUp(self):
        # mock 主程序依赖
        self._mock_app_deps()
        from PyQt5.QtWidgets import QApplication
        self._app = QApplication.instance() or QApplication(sys.argv)

        # 加载 ChessCard（之前需 mock qfluentwidgets 和 PluginConfigStore）
        from app.plugins.managers import plugin_config_store
        store = plugin_config_store.PluginConfigStore.return_value
        store.get.side_effect = lambda p, k, d=None: {"red_control": "manual"}.get(k, d)
        store.set_values = MagicMock()
        store.get_values = MagicMock(return_value={})

        from ui.chess_board import ChessCard
        self.card = ChessCard()
        self.card._board_view._animating = False
        # 激活棋盘以便 set_pieces 工作
        self.card._board_view.show()

    def _mock_app_deps(self):
        mod_app_plugins = types.ModuleType("app")
        mod_plugins = types.ModuleType("app.plugins")
        mod_managers = types.ModuleType("app.plugins.managers")
        mod_store = types.ModuleType("app.plugins.managers.plugin_config_store")
        mod_store.PluginConfigStore = MagicMock()
        mod_managers.plugin_config_store = mod_store
        mod_regs = types.ModuleType("app.plugins.registries")
        mod_reg = types.ModuleType("app.plugins.registries.ui_plugin_registry")
        mod_reg.UIPluginRegistry = MagicMock()
        mod_reg.UIPluginRegistry.get_instance.return_value = MagicMock(_settings_cards={})
        mod_regs.ui_plugin_registry = mod_reg
        mod_app_plugins.plugins = mod_plugins
        mod_plugins.managers = mod_managers
        mod_plugins.registries = mod_regs
        sys.modules["app"] = mod_app_plugins
        sys.modules["app.plugins"] = mod_plugins
        sys.modules["app.plugins.managers"] = mod_managers
        sys.modules["app.plugins.managers.plugin_config_store"] = mod_store
        sys.modules["app.plugins.registries"] = mod_regs
        sys.modules["app.plugins.registries.ui_plugin_registry"] = mod_reg
        # qfluentwidgets
        qfw = types.ModuleType("qfluentwidgets")
        qfw.InfoBar = MagicMock()
        qfw.InfoBarPosition = MagicMock()
        qfw.PushButton = MagicMock()
        qfw.ExpandSettingCard = MagicMock()
        qfw.FluentIcon = MagicMock()
        sys.modules["qfluentwidgets"] = qfw

    def test_animating_blocks_click(self):
        """_animating=True 时 _on_board_click 应直接返回"""
        self.card._board_view._animating = True
        # mock _select_piece 应不被调用
        self.card._select_piece = MagicMock()
        self.card._on_board_click(1, 9)  # 红马 (1,9)
        self.card._select_piece.assert_not_called()

    def test_animating_blocks_apply_move(self):
        """_animating=True 时 _apply_move 应跳过"""
        from ui.game_logic import make_move
        original_board = [row[:] for row in self.card._board]
        self.card._board_view._animating = True
        self.card._apply_move((0, 9, 0, 8))  # 红车前进一步
        # 棋盘不应改变
        self.assertEqual(self.card._board, original_board)

    def test_normal_mode_processes_click(self):
        """_animating=False（默认）时点击正常处理"""
        # 不动 _animating，验证默认 False
        self.assertFalse(self.card._board_view._animating)
        self.card._select_piece = MagicMock()
        self.card._on_board_click(1, 9)
        self.card._select_piece.assert_called_once_with(1, 9)

    def test_manual_click_moves_piece(self):
        """P0 回归：手动点击走子不再抛 NameError(source 未定义)，且落子生效"""
        # 模拟用户反馈的崩溃路径：手动模式红方点击落子
        self.card._red_control = "manual"
        self.card._side_to_move = RED
        self.card._game_over = False
        self.card._start_ai_move = MagicMock()  # 阻止真实 AI 线程副作用
        # 选中红车 (0,9) 后点击目标格 (0,8) 走子
        self.card._on_board_click(0, 9)
        self.card._on_board_click(0, 8)
        # 红车应到达 (0,8)，原 (0,9) 变空
        self.assertEqual(self.card._board[8][0], "R")
        self.assertEqual(self.card._board[9][0], ".")


if __name__ == "__main__":
    unittest.main(verbosity=2)
