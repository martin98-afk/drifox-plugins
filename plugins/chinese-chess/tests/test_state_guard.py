# -*- coding: utf-8 -*-
"""状态机代际守卫 + 非法 AI 走法拦截测试（#9 / Blocker #1）

覆盖：
- _gen_id 代际守卫：新对局自增；旧局 AI 结果被丢弃；当前局结果生效
- _apply_move 对非法 AI 走法拦截（source=llm/fallback），玩家手动走子不受校验影响
"""

import sys
import os
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PySide6.QtWidgets import QApplication  # noqa: F401

_app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841

from ui.chess_board import ChessCard
from ui.game_logic import gen_legal_moves


class TestGenerationGuard(unittest.TestCase):
    """_gen_id 代际守卫：旧局 AI 结果被丢弃，当前局生效。"""

    def test_new_game_increments_gen_id(self):
        card = ChessCard()
        old = card._gen_id
        card._new_game()
        self.assertEqual(card._gen_id, old + 1)

    def test_old_generation_ai_result_discarded(self):
        card = ChessCard()
        old_gen = card._gen_id
        card._gen_id += 1  # 新对局已开始
        board_before = [row[:] for row in card._board]
        # 旧代际任务回调（即便走法合法也拦截）
        card._on_ai_done((0, 9, 0, 8), "llm", "", gen_id=old_gen)
        self.assertEqual(card._board, board_before)

    def test_current_generation_ai_result_applied(self):
        card = ChessCard()
        board_before = [row[:] for row in card._board]
        card._start_ai_move = MagicMock()  # 防止触发真实 AI 线程
        card._on_ai_done((0, 9, 0, 8), "llm", "", gen_id=card._gen_id)
        self.assertNotEqual(card._board, board_before)
        self.assertEqual(card._side_to_move, "black")
        card._start_ai_move.assert_called_once()


class TestIllegalAIMoveGuard(unittest.TestCase):
    """_apply_move 对非法 AI 走法拦截（不落子）。"""

    def test_illegal_ai_move_rejected(self):
        card = ChessCard()
        board_before = [row[:] for row in card._board]
        illegal = (0, 9, 2, 8)  # 红车斜走，非法
        self.assertNotIn(illegal, gen_legal_moves(card._board, card._side_to_move))
        card._apply_move(illegal, source="llm")
        self.assertEqual(card._board, board_before)

    def test_fallback_ai_move_invalid_rejected(self):
        card = ChessCard()
        board_before = [row[:] for row in card._board]
        illegal = (0, 9, 3, 7)  # 非法走法
        card._apply_move(illegal, source="fallback")
        self.assertEqual(card._board, board_before)

    def test_legal_ai_move_applied(self):
        card = ChessCard()
        board_before = [row[:] for row in card._board]
        card._start_ai_move = MagicMock()
        card._apply_move((0, 9, 0, 8), source="llm")
        self.assertNotEqual(card._board, board_before)
        card._start_ai_move.assert_called_once()

    def test_manual_move_no_legality_check(self):
        """玩家手动走子不传 source，合法走法正常落子。"""
        card = ChessCard()
        board_before = [row[:] for row in card._board]
        card._apply_move((0, 9, 0, 8))  # 不传 source
        self.assertNotEqual(card._board, board_before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
