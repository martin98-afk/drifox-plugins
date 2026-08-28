# -*- coding: utf-8 -*-
"""中国象棋手动控制模式测试

校验：red_control=manual 时红方走子不调 AI；切到 ai 时启动 AI。
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 必须在导入 ChessCard 之前 mock qfluentwidgets（避免 GUI 依赖）
import types
from unittest.mock import MagicMock


def _ensure_qfluent_stubs():
    if "qfluentwidgets" in sys.modules:
        return
    qfw = types.ModuleType("qfluentwidgets")
    qfw.InfoBar = MagicMock()
    qfw.InfoBarPosition = MagicMock()
    qfw.PushButton = MagicMock()
    qfw.ExpandSettingCard = MagicMock()
    qfw.FluentIcon = MagicMock()
    sys.modules["qfluentwidgets"] = qfw


def _ensure_app_stubs():
    """mock 主程序 app.plugins.* 子树，避免 ChessCard import 时崩。"""
    mod_app_plugins = types.ModuleType("app")
    mod_plugins = types.ModuleType("app.plugins")
    mod_managers = types.ModuleType("app.plugins.managers")
    mod_store = types.ModuleType("app.plugins.managers.plugin_config_store")
    mod_store.PluginConfigStore = MagicMock(return_value=MagicMock())
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


_ensure_qfluent_stubs()
_ensure_app_stubs()


# 必须在 mock 之后导入
from PySide6.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841

from ui.chess_board import ChessCard  # noqa: E402
from ui.game_logic import RED, BLACK, initial_board  # noqa: E402


def _patch_store_with(values):
    """让 PluginConfigStore.get() 返回预定义 values。"""
    from app.plugins.managers import plugin_config_store

    store = plugin_config_store.PluginConfigStore.return_value
    store.get.side_effect = lambda plugin, key, default=None: values.get(key, default)
    store.set_values = MagicMock()
    store.get_values = MagicMock(return_value=values)


def _make_card(red_control="manual", red_model="", black_model=""):
    """构造一个 ChessCard 实例，注入 fake 配置。"""
    _patch_store_with(
        {
            "red_control": red_control,
            "red_model": red_model,
            "black_model": black_model,
        }
    )
    return ChessCard()


class TestRedControlMode(unittest.TestCase):
    """red_control 模式正确分支决定是否启动 AI。"""

    def test_manual_default(self):
        """默认值 = manual。"""
        card = _make_card()
        self.assertEqual(card._red_control, "manual")

    def test_loaded_from_store(self):
        """从 store 加载 ai 模式。"""
        card = _make_card(red_control="ai")
        self.assertEqual(card._red_control, "ai")

    def test_update_config_runtime(self):
        """运行时切换 control 模式立即生效。"""
        card = _make_card(red_control="manual")
        card.update_config({"red_control": "ai"})
        self.assertEqual(card._red_control, "ai")

        card.update_config({"red_control": "manual"})
        self.assertEqual(card._red_control, "manual")

    def test_update_config_model(self):
        """运行时更新 model 配置立即生效。"""
        card = _make_card()
        card.update_config({"red_model": "OpenAI:gpt-4o"})
        self.assertEqual(card._red_model, "OpenAI:gpt-4o")
        card.update_config({"black_model": "DeepSeek:deepseek-chat"})
        self.assertEqual(card._black_model, "DeepSeek:deepseek-chat")


class TestManualNoAICalled(unittest.TestCase):
    """manual 模式：红方走子后切到 BLACK → AI 接管黑方（永远）。"""

    def test_manual_mode_ai_runs_for_black_after_red_move(self):
        """manual 模式：红走子 → _side_to_move = BLACK → 启动 black AI（控制方式不影响黑方）"""
        card = _make_card(red_control="manual")
        card._setup_ui = MagicMock()
        card._start_ai_move = MagicMock()

        from ui.game_logic import initial_board as _ib
        card._board = _ib()
        card._side_to_move = RED
        card._game_over = False
        card._ai_task = None

        # 红车前进一步（合法走法）
        card._apply_move((0, 9, 0, 8))
        card._start_ai_move.assert_called_once()
        # 应以 side_label='black' 启动（黑方始终由 AI 控制）
        args, kwargs = card._start_ai_move.call_args
        self.assertEqual(kwargs.get("side_label", args[0] if args else None), "black")

    def test_manual_mode_no_red_ai_ever(self):
        """manual 模式：永远不会启动 side_label='red' 的 AI（红方由玩家掌控）"""
        card = _make_card(red_control="manual")
        card._setup_ui = MagicMock()
        card._start_ai_move = MagicMock()

        from ui.game_logic import initial_board as _ib
        card._board = _ib()

        # 模拟红走子（任一合法走法）
        card._side_to_move = RED
        card._apply_move((0, 9, 0, 8))
        # 没有任何调用以 side_label='red' 启动
        if card._start_ai_move.called:
            args, kwargs = card._start_ai_move.call_args
            self.assertNotEqual(
                kwargs.get("side_label", args[0] if args else None),
                "red",
                "manual 模式绝不能启动红方 AI",
            )

    def test_red_control_ai_triggers_red_ai_after_black_move(self):
        """ai 模式：黑方走子后轮到红方 → 启动 red AI"""
        card = _make_card(red_control="ai")
        card._setup_ui = MagicMock()
        card._start_ai_move = MagicMock()

        from ui.game_logic import initial_board as _ib
        card._board = _ib()
        card._side_to_move = BLACK  # 黑方先走
        card._game_over = False
        card._ai_task = None

        # 黑车前进一步（合法走法）
        card._apply_move((0, 0, 0, 1))
        # 应启动红方 AI（切到 RED + red_control=ai）
        card._start_ai_move.assert_called_once()
        args, kwargs = card._start_ai_move.call_args
        self.assertEqual(kwargs.get("side_label", args[0] if args else None), "red")


class TestControlGuard(unittest.TestCase):
    """AI 思考期间 / 手动模式切换期间点击应正确拦截。"""

    def test_ai_control_red_blocks_click(self):
        """红方 + ai 模式：玩家点击被忽略（AI 在思考）。"""
        card = _make_card(red_control="ai")
        # 假装 AI 正在运行
        card._ai_task = object()  # 任何非 None 占位

        # _side_to_move = RED, red_control = ai → 拒绝
        card._game_over = False
        card._side_to_move = RED
        # _on_board_click 不应触发选择
        # 但 _select_piece 不太好测（涉及 widget 选中）
        # 这里改测 _on_board_click 在该情形下提早 return
        # 通过 mock _select_piece 调用次数
        original = card._select_piece
        card._select_piece = MagicMock()
        card._on_board_click(1, 7)
        card._select_piece.assert_not_called()
        card._select_piece = original

    def test_manual_red_allows_click(self):
        """红方 + manual：玩家点击应能选中棋子。"""
        card = _make_card(red_control="manual")
        card._game_over = False
        card._side_to_move = RED
        card._selected = None
        # 选 (1, 9) 处的红马（'H'）
        # 需要棋盘已设置
        from ui.game_logic import initial_board as _ib
        card._board = _ib()

        original = card._select_piece
        card._select_piece = MagicMock()
        # 点击红马所在 (1, 9) 不应被拦截
        card._on_board_click(1, 9)
        card._select_piece.assert_called_once_with(1, 9)
        card._select_piece = original

    def test_game_over_blocks_click(self):
        """对局结束 → 所有点击被忽略。"""
        card = _make_card()
        card._game_over = True
        from ui.game_logic import initial_board as _ib
        card._board = _ib()
        card._side_to_move = RED

        original = card._select_piece
        card._select_piece = MagicMock()
        card._on_board_click(1, 9)
        card._select_piece.assert_not_called()
        card._select_piece = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
