# -*- coding: utf-8 -*-
"""AI 思考记录面板测试（#7）

覆盖：
- strip_json_and_moves：fenced/裸/嵌套 JSON、走法正则、占位符合并、文本保留
- AIThoughtPanel.add_thought：step 自增、Markdown 片段构造、字符累计、空文本占位
- 复制 / 清空 / 折叠 / 状态栏
- 信号：_AISignals.thought_received emit → 连接
- 集成：ChessCard._on_thought_received 路由到面板（含 panel=None 安全）
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# QApplication 必须先存在
from PyQt5.QtWidgets import QApplication  # noqa: F401

_app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841

from ui.thought_panel import (
    AIThoughtPanel,
    strip_json_and_moves,
    PLACEHOLDER,
)
from ui.ai_engine import _AISignals
from ui.chess_board import ChessCard


# ──────────────────────────────────────────────────────────────
# 1) strip_json_and_moves 纯函数测试
# ──────────────────────────────────────────────────────────────

class TestStripJsonAndMoves(unittest.TestCase):
    """JSON / 走法剥离函数单元验证。"""

    def test_strips_fenced_json_block(self):
        text = '分析如下：\n```json\n{"from":[1,9],"to":[1,7]}\n```\n结束'
        out = strip_json_and_moves(text)
        self.assertIn(PLACEHOLDER, out)
        self.assertNotIn("from", out)
        self.assertNotIn("```", out)

    def test_strips_fenced_plain_code_block(self):
        text = '```\n{"from":[1,9],"to":[1,7]}\n```'
        out = strip_json_and_moves(text)
        self.assertIn(PLACEHOLDER, out)
        self.assertNotIn("from", out)

    def test_strips_bare_json_object(self):
        text = '我决定走 {"from":[4,9],"to":[4,8]} 这步'
        out = strip_json_and_moves(text)
        self.assertIn(PLACEHOLDER, out)
        self.assertNotIn("from", out)

    def test_strips_nested_json(self):
        text = '{"move":{"from":[1,9],"to":[1,7]},"score":0.9}'
        out = strip_json_and_moves(text)
        self.assertIn(PLACEHOLDER, out)
        self.assertNotIn("from", out)
        self.assertNotIn("score", out)

    def test_strips_move_regex(self):
        text = '{"from":[1,9],"to":[1,7]}'
        out = strip_json_and_moves(text)
        self.assertIn(PLACEHOLDER, out)
        self.assertNotIn("from", out)

    def test_keeps_normal_text(self):
        text = "红方应该先出动右翼车马炮，控制中心"
        out = strip_json_and_moves(text)
        self.assertEqual(out, text.strip())

    def test_empty_input_returns_empty(self):
        self.assertEqual(strip_json_and_moves(""), "")
        # 空白串经末尾 .strip() 归一为空字符串
        self.assertEqual(strip_json_and_moves("   "), "")

    def test_merges_consecutive_placeholders(self):
        # 代码块 + 紧接的裸 JSON → 合并为一个占位符
        text = '```json\n{"a":1}\n```\n{"b":2}'
        out = strip_json_and_moves(text)
        # 不应出现两个连续占位符
        self.assertNotIn(PLACEHOLDER + " " + PLACEHOLDER, out)
        self.assertEqual(out.count(PLACEHOLDER), 1)

    def test_keeps_explanation_strips_json(self):
        text = '我认为中路突破更好\n```json\n{"from":[4,9],"to":[4,8]}\n```'
        out = strip_json_and_moves(text)
        self.assertIn("中路突破", out)
        self.assertIn(PLACEHOLDER, out)
        self.assertNotIn("from", out)

    def test_multiple_code_blocks_all_stripped(self):
        text = '```json\n{"from":[1,9],"to":[1,7]}\n```\n中间说明\n```json\n{"from":[0,9],"to":[0,8]}\n```'
        out = strip_json_and_moves(text)
        self.assertNotIn("from", out)
        self.assertNotIn("```", out)
        self.assertIn("中间说明", out)


# ──────────────────────────────────────────────────────────────
# 2) AIThoughtPanel 组件测试
# ──────────────────────────────────────────────────────────────

class TestAIThoughtPanel(unittest.TestCase):
    """面板 add_thought / 复制 / 清空 / 折叠 / 状态栏。"""

    def setUp(self):
        self.panel = AIThoughtPanel()

    def test_initial_state(self):
        self.assertEqual(self.panel.get_step(), 0)
        self.assertEqual(self.panel.get_total_chars(), 0)

    def test_add_thought_returns_step(self):
        step = self.panel.add_thought("红", "gpt-4", "考虑中路突破")
        self.assertEqual(step, 1)
        self.assertEqual(self.panel.get_step(), 1)

    def test_add_thought_autoincrement(self):
        for i in range(5):
            self.panel.add_thought("红", "gpt-4", f"思考{i}")
        self.assertEqual(self.panel.get_step(), 5)
        # 文本含全部 5 个标题
        text = self.panel.get_text()
        for i in range(1, 6):
            self.assertIn(f"第 {i} 步", text)

    def test_add_thought_strips_json(self):
        self.panel.add_thought("红", "gpt-4", '{"from":[4,9],"to":[4,8]}')
        out = self.panel.get_text()
        self.assertIn(PLACEHOLDER, out)
        self.assertNotIn("from", out)

    def test_add_thought_accumulates_chars(self):
        self.panel.add_thought("红", "gpt-4", "abcdef")
        self.panel.add_thought("黑", "gpt-4", "123456")
        # 字符统计基于剥离后的文本；此处剥离后仍各 6 字符
        self.assertEqual(self.panel.get_total_chars(), 12)

    def test_add_thought_empty_text_placeholder(self):
        self.panel.add_thought("红", "gpt-4", "")
        out = self.panel.get_text()
        self.assertIn("无文本", out)

    def test_add_thought_header_has_side_and_model(self):
        self.panel.add_thought("黑", "claude-3", "走边线")
        out = self.panel.get_text()
        self.assertIn("黑", out)
        self.assertIn("claude-3", out)
        self.assertIn("第 1 步", out)

    def test_clear_all_resets(self):
        self.panel.add_thought("红", "gpt-4", "思考一些内容")
        self.assertEqual(self.panel.get_step(), 1)
        self.panel.clear_all()
        self.assertEqual(self.panel.get_step(), 0)
        self.assertEqual(self.panel.get_total_chars(), 0)
        self.assertEqual(self.panel.get_text(), "")

    def test_copy_all_calls_clipboard(self):
        self.panel.add_thought("红", "gpt-4", "复制到剪贴板")
        mock_clip = MagicMock()
        with patch.object(
            __import__("ui.thought_panel", fromlist=["QGuiApplication"]).QGuiApplication,
            "clipboard",
            return_value=mock_clip,
        ):
            self.panel.copy_all()
        mock_clip.setText.assert_called_once()

    def test_toggle_collapse_hides_text_browser(self):
        # isHidden 仅反映组件自身 setVisible 状态（不受父级未 show 影响）
        self.assertFalse(self.panel._text_browser.isHidden())
        self.panel._toggle_collapse()
        self.assertTrue(self.panel._text_browser.isHidden())
        self.assertTrue(self.panel._collapsed)
        self.panel._toggle_collapse()
        self.assertFalse(self.panel._text_browser.isHidden())
        self.assertFalse(self.panel._collapsed)

    def test_status_label_updates(self):
        self.panel.add_thought("红", "gpt-4", "内容")
        self.assertIn("1 条", self.panel._status_label.text())
        self.panel.clear_all()
        self.assertIn("0 条", self.panel._status_label.text())


# ──────────────────────────────────────────────────────────────
# 3) 信号 + ChessCard 集成测试
# ──────────────────────────────────────────────────────────────

class TestThoughtSignalIntegration(unittest.TestCase):
    """thought_received 信号 emit 与 ChessCard 路由。"""

    def test_signal_emits_and_received(self):
        sig = _AISignals()
        received = []
        sig.thought_received.connect(
            lambda side, model, raw: received.append((side, model, raw))
        )
        sig.thought_received.emit("红", "gpt-4", '{"from":[4,9],"to":[4,8]}')
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], ("红", "gpt-4", '{"from":[4,9],"to":[4,8]}'))

    def test_signal_to_panel_add_thought(self):
        sig = _AISignals()
        panel = AIThoughtPanel()
        sig.thought_received.connect(
            lambda side, model, raw: panel.add_thought(side, model, raw)
        )
        sig.thought_received.emit("黑", "claude-3", '{"from":[1,9],"to":[1,7]}')
        self.assertEqual(panel.get_step(), 1)
        self.assertIn(PLACEHOLDER, panel.get_text())
        self.assertNotIn("from", panel.get_text())

    def test_card_builds_panel(self):
        card = ChessCard()
        self.assertIsNotNone(card._thought_panel)
        self.assertIsInstance(card._thought_panel, AIThoughtPanel)

    def test_card_routes_thought_to_panel(self):
        card = ChessCard()
        before = card._thought_panel.get_step()
        card._on_thought_received(
            side_cn="红",
            model_name="gpt-4",
            raw_text='{"from":[4,9],"to":[4,8]}',
        )
        self.assertEqual(card._thought_panel.get_step(), before + 1)
        self.assertNotIn("from", card._thought_panel.get_text())

    def test_card_on_thought_safe_when_panel_none(self):
        card = ChessCard()
        card._thought_panel = None
        # 不应抛异常
        try:
            card._on_thought_received("红", "gpt-4", "任意文本")
        except Exception as e:  # noqa: BLE001
            self.fail(f"_on_thought_received 在 panel=None 时应安全返回: {e}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
