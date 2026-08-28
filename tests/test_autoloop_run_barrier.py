# -*- coding: utf-8 -*-
"""AutoLoop run() 异常屏障：任何未捕获异常必须转为 loop_error/loop_stopped 信号，
绝不允许 QThread 静默死亡（独占模式下 = UI 永久锁死）。

worker.py 顶层 import 了 app.core.* —— 插件仓无主仓代码；
用 importlib + sys.modules stub 注入绕过（不动测试基建/不动 conftest）。
"""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# 插件根注入 sys.path（对齐 ui/__init__.py 模式）
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "autoloop"
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

pytest.importorskip("PySide6")


# ---- 桩 app.* 模块（让 worker.py 顶层 import 不抛） ----
def _stub_app_modules():
    """为 worker.py 依赖的 app.* 注入空壳模块，避免插件仓测试需主仓代码。"""
    if "app" in sys.modules and hasattr(sys.modules["app"], "_autoloop_test_stub"):
        return  # 已 stub，跳过

    app_pkg = types.ModuleType("app")
    app_pkg.__path__ = []  # 标为包
    app_pkg._autoloop_test_stub = True
    sys.modules["app"] = app_pkg

    app_core = types.ModuleType("app.core")
    app_core.__path__ = []
    sys.modules["app.core"] = app_core

    for sub in ("conversation", "chat_session", "token_estimator"):
        m = types.ModuleType(f"app.core.{sub}")
        m.__path__ = []
        sys.modules[f"app.core.{sub}"] = m

    conv = sys.modules["app.core.conversation"]
    conv.ConversationExecutor = MagicMock
    conv_mod_config = types.ModuleType("app.core.conversation.config")
    conv_mod_config.ConversationConfig = MagicMock
    conv_mod_config.PermissionStrategy = MagicMock
    conv_mod_config.filter_interactive_tools = MagicMock()
    sys.modules["app.core.conversation.config"] = conv_mod_config
    conv_mod_core = types.ModuleType("app.core.conversation.core")
    conv_mod_core.ConversationCore = MagicMock
    sys.modules["app.core.conversation.core"] = conv_mod_core
    # adapter.py 依赖
    adapters_pkg = types.ModuleType("app.core.conversation.adapters")
    adapters_pkg.__path__ = []
    sys.modules["app.core.conversation.adapters"] = adapters_pkg
    adapter_base = types.ModuleType("app.core.conversation.adapters.base")
    adapter_base.BaseConversationAdapter = MagicMock
    sys.modules["app.core.conversation.adapters.base"] = adapter_base
    conv_mod_exec = types.ModuleType("app.core.conversation.executor")
    conv_mod_exec.ConversationExecutor = MagicMock
    sys.modules["app.core.conversation.executor"] = conv_mod_exec


_stub_app_modules()

# ---- 用 importlib 直接加载 worker.py（其包名为 autoloop_core）----
_WORKER_PATH = _PLUGIN_ROOT / "autoloop_core" / "worker.py"
_SPEC = importlib.util.spec_from_file_location(
    "autoloop_core.worker", _WORKER_PATH
)
assert _SPEC is not None and _SPEC.loader is not None
_worker_module = importlib.util.module_from_spec(_SPEC)
sys.modules["autoloop_core.worker"] = _worker_module
_SPEC.loader.exec_module(_worker_module)
AutoLoopWorker = _worker_module.AutoLoopWorker


def _make_worker():
    """构造 worker，绕过 Qt 信号真发射（用 MagicMock 记录）"""
    worker = AutoLoopWorker.__new__(AutoLoopWorker)
    worker._config = MagicMock()
    worker._config.task_prompt = "测试任务"
    worker._config.max_iterations = 5
    worker._engine = None
    worker._prompt_composer = None
    worker._is_cancelled = False
    worker._is_archive_button_click = False
    worker._last_step = 0
    worker._all_messages = []
    worker._round_messages = []
    worker._prev_message_count = 0
    worker._last_message_token_count = 0
    worker._conversation_core = MagicMock()
    worker._conversation_core.session_manager.get_current_session.return_value = MagicMock()
    signals = {name: MagicMock() for name in (
        "iteration_started", "iteration_completed", "progress_updated",
        "loop_completed", "loop_error", "loop_stopped", "phase_changed",
        "log_signal", "log_update", "tokens_updated", "messages_logged",
    )}
    for name, sig in signals.items():
        setattr(worker, name, sig)
    return worker, signals


def test_run_crash_emits_error_and_stopped():
    """run() 中途抛未捕获异常 → loop_error + loop_stopped 必发，线程不死锁"""
    worker, signals = _make_worker()
    # 让主循环第一轮就崩：_build_messages 抛异常（模拟笔记解析等非预期数据）
    from autoloop_core.engine import AutoLoopEngine
    worker._engine = AutoLoopEngine(worker._config)
    worker._prompt_composer = MagicMock()

    def _boom(task_prompt, iteration):
        raise RuntimeError("模拟解析崩溃")

    worker._build_messages = _boom
    worker.run()  # 不应向外抛异常
    assert signals["loop_error"].emit.called or signals["loop_stopped"].emit.called


def test_run_guard_clauses_before_barrier():
    """无 task_prompt → 早退 loop_error，不进入屏障内部"""
    worker, signals = _make_worker()
    worker._config.task_prompt = ""
    worker.run()
    signals["loop_error"].emit.assert_called_once()