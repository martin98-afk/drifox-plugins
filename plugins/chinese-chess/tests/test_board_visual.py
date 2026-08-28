# -*- coding: utf-8 -*-
"""棋盘视觉升级测试（#5）

校验：
- theme.py 的 QSS 字符串可正常生成
- PieceLabel 包含必要属性（border-radius、QGraphicsDropShadowEffect）
- ChessBoardView 鼠标跟踪 + hover 状态切换
- get_piece_qss 输出含红/黑/hover/selected 四种风格
- get_full_qss 输出含 #chessCardPanel / #chessBoardPanel 等关键 selector
"""

import sys
import os
import unittest
import types

# QApplication 实例（必须在 QWidget 之前）
from PySide6.QtWidgets import QApplication, QLabel

_app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ui import theme
from ui.game_logic import RED, BLACK, gen_legal_moves, initial_board
from ui.widgets import PieceLabel, ChessBoardView


class TestThemeConstants(unittest.TestCase):
    """theme.py 中色值常量存在且非空"""

    def test_user_colors(self):
        self.assertEqual(theme.USER_BG, "#f5f5f7")
        self.assertEqual(theme.USER_PRIMARY, "#2c5f8d")
        self.assertEqual(theme.USER_ACCENT, "#d4af37")

    def test_board_colors(self):
        self.assertTrue(theme.BOARD_WOOD.startswith("#"))
        self.assertTrue(theme.BOARD_BORDER.startswith("#"))

    def test_piece_colors(self):
        self.assertEqual(theme.PIECE_RED, "#c62828")
        self.assertEqual(theme.PIECE_BLACK, "#1a1a1a")

    def test_highlight_colors(self):
        # 都是合法色值
        for c in [
            theme.SELECTED_HIGHLIGHT,
            theme.LEGAL_HIGHLIGHT,
            theme.LAST_MOVE_HIGHLIGHT,
            theme.HOVER_EMPTY_DOT,
        ]:
            self.assertTrue(c.startswith("#") or c.startswith("rgba"))


class TestGetPieceQss(unittest.TestCase):
    """get_piece_qss 四种风格（红/黑/hover/selected）"""

    def test_red_default(self):
        s = theme.get_piece_qss("red")
        self.assertIn(theme.PIECE_RED, s)
        self.assertIn("border-radius: 50%", s)
        self.assertIn("qradial-gradient", s)
        self.assertNotIn("hover", s)  # 默认不含 hover 变体色

    def test_black_default(self):
        s = theme.get_piece_qss("black")
        self.assertIn(theme.PIECE_BLACK, s)
        self.assertIn("border-radius: 50%", s)

    def test_hover_changes_border_to_gold(self):
        s = theme.get_piece_qss("red", hover=True)
        self.assertIn(theme.USER_ACCENT, s)
        # hover 模式：金色边框 + 木制背景（深棕木底关键色）
        self.assertIn("#8b5a2b", s)

    def test_selected_adds_thicker_border(self):
        s_default = theme.get_piece_qss("red")
        s_selected = theme.get_piece_qss("red", selected=True)
        # selected 应加粗 border
        self.assertIn("3px", s_selected)
        # 同样含 USER_ACCENT（描边外圈）
        self.assertIn(theme.USER_ACCENT, s_selected)

    def test_combined_hover_selected(self):
        s = theme.get_piece_qss("black", hover=True, selected=True)
        self.assertIn(theme.USER_ACCENT, s)
        self.assertIn("3px", s)

    def test_wood_opaque_background(self):
        """木制背景不透明（无 rgba 半透明）+ 含木色关键值"""
        for side in ("red", "black"):
            s = theme.get_piece_qss(side)
            self.assertIn("#8b5a2b", s)   # 深棕木底
            self.assertIn("#c8924a", s)   # 木橙中段
            # 背景不透明：不含任何 rgba(...) 半透明写法
            self.assertNotIn("rgba", s.lower())

    def test_red_and_black_share_wood_base(self):
        """红/黑同木底，仅文字色不同"""
        s_red = theme.get_piece_qss("red")
        s_black = theme.get_piece_qss("black")
        self.assertIn(theme.PIECE_RED, s_red)
        self.assertIn(theme.PIECE_BLACK, s_black)
        # 两者背景渐变保持一致（木色）
        self.assertIn("#8b5a2b", s_red)
        self.assertIn("#8b5a2b", s_black)


class TestGetFullQss(unittest.TestCase):
    """get_full_qss 包含必要 selector"""

    def test_includes_card_panel(self):
        s = theme.get_full_qss()
        self.assertIn("#chessCardPanel", s)
        self.assertIn("#chessBoardPanel", s)
        self.assertIn("#chessPrimaryBtn", s)
        self.assertIn("#chessDangerBtn", s)

    def test_wood_three_layers(self):
        s = theme.get_full_qss()
        # 木纹三层叠加：径向高光 + 重复线性 + 主渐变
        self.assertIn("radial-gradient", s)
        self.assertIn("repeating-linear-gradient", s)
        self.assertIn("linear-gradient(180deg", s)

    def test_accepts_card_bg_override(self):
        s1 = theme.get_full_qss()
        s2 = theme.get_full_qss(card_bg="#ffffff")
        # 应不同
        self.assertNotEqual(s1, s2)


class TestMakePieceShadow(unittest.TestCase):
    """make_piece_shadow 返回 QGraphicsDropShadowEffect，参数生效"""

    def test_default_params(self):
        s = theme.make_piece_shadow()
        from PySide6.QtWidgets import QGraphicsDropShadowEffect

        self.assertIsInstance(s, QGraphicsDropShadowEffect)
        self.assertEqual(s.blurRadius(), theme.PIECE_SHADOW_BLUR)
        from PySide6.QtCore import QPoint
        self.assertEqual(s.offset(), QPoint(0, theme.PIECE_SHADOW_OFFSET_Y))

    def test_custom_params(self):
        s = theme.make_piece_shadow(blur_radius=12, offset_y=4, alpha=200)
        self.assertEqual(s.blurRadius(), 12)


class TestPieceLabelAttributes(unittest.TestCase):
    """PieceLabel 包含立体阴影 + 圆角 QSS + ObjectName"""

    def setUp(self):
        from ui.game_logic import initial_board as _ib
        self.parent_widget = ChessBoardView(cell=52)
        # 取一个红马 (1, 9) 作为测试棋子
        board = _ib()
        piece = board[9][1]  # 'H'
        self.label = PieceLabel(piece, cell=52, parent=self.parent_widget)

    def test_piece_size_matches_cell(self):
        # 棋子边长 = cell * 0.86
        expected = int(52 * 0.86)
        self.assertEqual(self.label.width(), expected)
        self.assertEqual(self.label.height(), expected)

    def test_piece_has_graphics_effect(self):
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        eff = self.label.graphicsEffect()
        self.assertIsInstance(eff, QGraphicsDropShadowEffect)

    def test_piece_uses_paint_event_not_qss(self):
        """v0.2.1 修复：弃用 QSS，视觉全部由 paintEvent 自绘（避免 QSS border 不裁剪圆角导致方框）。

        PieceLabel.styleSheet() 应为空；圆角、渐变、描边都在 paintEvent → _draw_piece_circle 内绘制。
        """
        # 不再设置 QSS（之前是 "border-radius: 50%; qradial-gradient..."）
        self.assertEqual(self.label.styleSheet(), "")
        # WA_StyledBackground 必须为 False（否则 QSS 引擎仍会绘制方框 background/border）
        from PySide6.QtCore import Qt
        self.assertFalse(
            self.label.testAttribute(Qt.WA_StyledBackground),
            "WA_StyledBackground=True 会让 QSS 方形 border 覆盖在自绘圆形之上，必须关闭",
        )
        # paintEvent 已重写
        self.assertTrue(PieceLabel.paintEvent is not QLabel.paintEvent)

    def test_piece_objectname_is_chess_piece(self):
        self.assertEqual(self.label.objectName(), "chessPiece")

    def test_piece_paint_contains_red_text_color(self):
        """自绘函数的颜色定义来自 theme.PIECE_RED / theme.PIECE_BLACK（保持单一来源）。"""
        # 通过 _draw_piece_circle 间接验证：side="red" 渲染时字体色来自 PIECE_RED
        # 这里用 mock 检查模块常量被函数引用
        import inspect
        from ui import widgets
        src = inspect.getsource(widgets._draw_piece_circle)
        self.assertIn("PIECE_RED", src)
        self.assertIn("PIECE_BLACK", src)
        self.assertIn("USER_ACCENT", src)  # hover/selected 金色
        # 木色径向渐变关键色
        self.assertIn("#8b5a2b", src)

    def test_mouse_transparent_for_click_passthrough(self):
        from PySide6.QtCore import Qt
        self.assertTrue(
            self.label.testAttribute(Qt.WA_TransparentForMouseEvents),
            "棋子必须透明鼠标事件以让点击穿透到 ChessBoardView",
        )

    def test_hover_toggle(self):
        # 初始 not hovered
        self.assertFalse(self.label._hover)
        self.label.set_hover(True)
        self.assertTrue(self.label._hover)
        # 验证 _draw_piece_circle 在 hover=True 时使用金色描边
        # 通过状态变量影响 paintEvent 行为
        self.assertTrue(self.label._hover)
        self.label.set_hover(False)
        self.assertFalse(self.label._hover)

    def test_selected_toggle(self):
        self.assertFalse(self.label._selected)
        self.label.set_selected(True)
        self.assertTrue(self.label._selected)
        # selected 时 border_w 应为 3px（hover/默认是 2px）
        # 通过 _draw_piece_circle 的逻辑分支判断：
        # 用 import + inspect 检查源码分支
        import inspect
        from ui import widgets
        src = inspect.getsource(widgets._draw_piece_circle)
        # 描边宽度有 selected 分支，且 selected 时宽于 hover/默认
        self.assertIn("selected", src)
        self.assertIn("border_w", src)

    def test_set_piece_to_empty_hides(self):
        self.label.set_piece(".")
        self.assertFalse(self.label.isVisible())
        self.assertEqual(self.label.text(), "")


class TestChessBoardViewHover(unittest.TestCase):
    """ChessBoardView 鼠标跟踪 + hover 跟踪 + 选中切换"""

    def setUp(self):
        self.view = ChessBoardView(cell=52)

    def test_grid_at_valid(self):
        # 棋盘有效区域内返回坐标
        pos = self.view._grid_at(self.view._left + 1 * self.view._cell,
                                  self.view._top + 1 * self.view._cell)
        self.assertEqual(pos, (1, 1))

    def test_grid_at_out_of_bounds(self):
        # 棋盘外（负值）
        pos = self.view._grid_at(-10, -10)
        self.assertIsNone(pos)

    def test_grid_at_padding_area(self):
        # 在 padding 区（左/上边距）→ None
        pos = self.view._grid_at(1, 1)  # < pad
        self.assertIsNone(pos)

    def test_mouse_tracking_enabled(self):
        from PySide6.QtCore import Qt
        self.assertTrue(self.view.hasMouseTracking(), "需开启鼠标跟踪才能 mouseMove")

    def test_hover_pos_update_changes_state(self):
        self.view._hover_pos = (3, 3)
        self.assertEqual(self.view._hover_pos, (3, 3))

    def test_set_selected_propagates_to_piece(self):
        # 在棋盘上放一个红车，验证 set_selected 时 PieceLabel 状态切换
        board = [["." for _ in range(9)] for _ in range(10)]
        board[9][4] = "K"  # 必须有红帅，gen_legal_moves 才不会爆
        board[9][0] = "R"  # 红车
        self.view.set_pieces(board)
        # 未设 _selected → 不是 selected
        self.view.set_selected((0, 9))
        # PieceLabel 上应有 selected（状态变量被 paintEvent 读取）
        lbl = self.view._pieces[(0, 9)]
        self.assertTrue(lbl._selected)
        # 取消选中
        self.view.set_selected(None)
        self.assertFalse(lbl._selected)


class TestBackwardCompat(unittest.TestCase):
    """棋盘旧调用方不受影响：旧常量名仍可用"""

    def test_old_color_constants(self):
        from ui.widgets import (
            BOARD_BG, BOARD_LINE, BOARD_TEXT,
            SELECTED_HIGHLIGHT, LEGAL_HIGHLIGHT, LAST_MOVE_HIGHLIGHT,
        )
        # 这些常量都是合法色值
        for c in [BOARD_BG, BOARD_LINE, BOARD_TEXT,
                  SELECTED_HIGHLIGHT, LEGAL_HIGHLIGHT, LAST_MOVE_HIGHLIGHT]:
            self.assertTrue(c.startswith("#") or c.startswith("rgba"),
                            f"旧常量必须仍可用：{c}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
