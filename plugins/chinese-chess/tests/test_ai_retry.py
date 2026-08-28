# -*- coding: utf-8 -*-
"""AI 引擎解析失败重试测试

校验 fix：空响应 / 解析失败 → 重试 2 次后兜底走 fallback_legal_move（非 random）。
"""
import sys
import os
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ui import ai_engine
from ui.game_logic import RED, ROWS, COLS, initial_board, gen_legal_moves
from ui.ai_engine import (
    parse_move,
    fallback_legal_move,
    _AISignals,
    _AIMoveTask,
)


class TestParseMoveTuple(unittest.TestCase):
    """parse_move 现在返回 (move, error_msg) 二元组。"""

    def test_valid_json(self):
        text = '{"from":[1,9],"to":[1,7]}'
        move, err = parse_move(text)
        self.assertEqual(move, (1, 9, 1, 7))
        self.assertEqual(err, "")

    def test_empty_response(self):
        move, err = parse_move("")
        self.assertIsNone(move)
        self.assertEqual(err, "empty_response")

    def test_no_json(self):
        move, err = parse_move("我无法识别此局面")
        self.assertIsNone(move)
        self.assertEqual(err, "no_json")

    def test_think_only_unclosed(self):
        # 思考块未闭合 → 截断
        move, err = parse_move("<think>I should move the horse... but ")
        self.assertIsNone(move)
        self.assertEqual(err, "think_only")

    def test_thinking_then_valid_json(self):
        text = '<think>reasoning</think>\n\n{"from":[4,9],"to":[4,8]}'
        move, err = parse_move(text)
        # 帅从 (4,9) 走到 (4,8) 是合法走法
        self.assertIsNotNone(move)
        self.assertEqual(err, "")
        self.assertEqual(move, (4, 9, 4, 8))

    def test_out_of_range(self):
        move, err = parse_move('{"from":[1,9],"to":[20,7]}')
        self.assertIsNone(move)
        self.assertEqual(err, "out_of_range")


class TestFallbackLegalMove(unittest.TestCase):
    """fallback_legal_move 不再 random，必须确定性且优先吃子。"""

    def test_returns_a_legal_move(self):
        board = initial_board()
        m = fallback_legal_move(board, RED)
        self.assertIsNotNone(m)
        self.assertIn(m, gen_legal_moves(board, RED))

    def test_no_randomness(self):
        """同局面调用两次返回相同走法（确定）。"""
        board = initial_board()
        m1 = fallback_legal_move(board, RED)
        m2 = fallback_legal_move(board, RED)
        self.assertEqual(m1, m2)

    def test_picks_capture_when_available(self):
        """有吃子走法时优先选择（构造简单情形）。"""
        from ui.game_logic import ROWS, COLS

        board = [["." for _ in range(COLS)] for _ in range(ROWS)]
        # 红帅 + 红车 + 黑车紧贴红车上方 = 唯一合法走法是吃车
        board[9][4] = "K"   # 红帅
        board[9][0] = "R"   # 红车 (0, 9)
        board[8][0] = "r"   # 黑车紧贴红车上方 (0, 8)

        m = fallback_legal_move(board, RED)
        legal = list(gen_legal_moves(board, RED))
        # 应有走法：吃车 + 帅能走
        self.assertIn((0, 9, 0, 8), legal, f"红车吃黑车的走法应在合法列表，got {legal}")
        # 兜底走法：吃黑车是更高优先级（车价值 90 > 帅走空格）
        # 但帅吃车不算 —— 帅不吃车会被 gen_legal_moves 过滤（送将）
        # 红帅 (4,9) → (4,8) 看似合法，但前提是黑帅不在攻击 4,8 —— 这里无黑帅
        # 红车 (0,9)→(0,8) 吃黑车是合法走法
        # 兜底走法优先吃子
        # 注意：fallback_legal_move 返回的第一个走法如果可以吃车，就是 (0,9,0,8)
        # 但若 (4,9)→(4,8) 这类空格走法的目标 board[8][4]='.' 价值 0，而吃车 90
        # 按 sort 排序后吃车应排第一
        self.assertEqual(m, (0, 9, 0, 8))


class TestRetryLogic(unittest.TestCase):
    """_AIMoveTask.run() 重试 + 兜底走 fallback_legal_move。"""

    def test_empty_then_valid_triggers_llm_path(self):
        """第一次空响应 → 重试 → 第二次合法 JSON → 走 llm 路径（不走 fallback）。"""
        signals = _AISignals()
        done_calls = []
        signals.done.connect(lambda m, s, r: done_calls.append((m, s, r)))

        # mock _one_shot_ask：第一次空，第二次合法走法
        # 红车 (0,9) → (0,8)（前进一步，无障碍，合法）
        responses = iter(
            [
                ("", "stop"),
                ('{"from":[0,9],"to":[0,8]}', "stop"),
            ]
        )

        def fake_ask(self, user_prompt, retry_hint=None):
            text, fr = next(responses)
            return text, fr

        task = _AIMoveTask(
            board=initial_board(),
            side=RED,
            history=[],
            llm_config={"API_KEY": "x", "API_URL": "http://x", "模型名称": "gpt-4"},
            signals=signals,
        )
        # patch 方法
        task._one_shot_ask = fake_ask.__get__(task, _AIMoveTask)

        task.run()

        self.assertEqual(len(done_calls), 1, f"expect 1 done signal, got {done_calls}")
        move, source, reason = done_calls[0]
        self.assertEqual(source, "llm", f"应走 LLM 路径，got: source={source}, reason={reason}")
        self.assertEqual(move, (0, 9, 0, 8))

    def test_all_retries_fail_then_fallback(self):
        """3 次全部空响应 → 走 fallback（非 random）。"""
        signals = _AISignals()
        done_calls = []
        signals.done.connect(lambda m, s, r: done_calls.append((m, s, r)))

        def fake_ask(self, user_prompt, retry_hint=None):
            return ("", "stop")

        task = _AIMoveTask(
            board=initial_board(),
            side=RED,
            history=[],
            llm_config={"API_KEY": "x", "API_URL": "http://x", "模型名称": "gpt-4"},
            signals=signals,
        )
        task._one_shot_ask = fake_ask.__get__(task, _AIMoveTask)

        task.run()

        self.assertEqual(len(done_calls), 1)
        move, source, reason = done_calls[0]
        # 兜底走法（源 = fallback）
        self.assertEqual(source, "fallback")
        self.assertIsNotNone(move, "兜底走法不应为 None")
        self.assertIn(move, gen_legal_moves(initial_board(), RED))
        # reason 应含 error 详情
        self.assertIn("empty_response", reason)

    def test_done_signal_three_args(self):
        """done 信号签名变更为 (move, source, reason) 三元组。"""
        signals = _AISignals()
        # Signal 在 mock 模式下不强校验参数数量，但 type 应兼容
        # 这里只验证 signatures 不冲突
        # 用一个真实 receiver 试一次
        captured = []

        def rec(m, s, r):
            captured.append((m, s, r))

        signals.done.connect(rec)

        signals.done.emit((0, 9, 0, 8), "llm", "")
        self.assertEqual(captured, [((0, 9, 0, 8), "llm", "")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
