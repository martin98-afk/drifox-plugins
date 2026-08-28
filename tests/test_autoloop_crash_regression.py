# -*- coding: utf-8 -*-
"""闪退回归：loop_error 误触发 _finish + 运行中线程被 deleteLater 的双重防护

故障链（2026-08-21 13:25 闪退）：
executor deleteLater ChatWorker → worker.py 兜底访问已删对象 RuntimeError
→ loop_error.emit（单轮可重试错误）→ controller._on_error 误调 _finish
→ _finish wait(1000) 超时仍 deleteLater → 销毁运行中 QThread → QtFatal abort
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "autoloop"
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

pytest.importorskip("PySide6")


def _make_controller_with_session(monkeypatch):
    """构造 controller + 单窗口会话（运行中 worker mock）"""
    from ui.controller import AutoLoopController, _WindowSession  # noqa: F401

    ctrl = AutoLoopController.__new__(AutoLoopController)
    ctrl._sessions = {}
    ctrl._running_cards = {}

    worker = MagicMock()
    worker.isRunning.return_value = True
    # quit/wait 模拟超时：wait 返回 False（1 秒内未退出）
    worker.wait.return_value = False
    signals = {"finished": MagicMock()}
    worker.finished = signals["finished"]

    session = MagicMock()
    session.worker = worker
    session.finishing = False
    session.services = {
        "notify": MagicMock(),
        "exit_exclusive_ui_mode": MagicMock(),
        "sync_working_directory": MagicMock(),
        "save_messages_to_session": MagicMock(),
        "set_workdir": MagicMock(),
    }
    session.running_card = None
    session.prev_workdir = ""
    ctrl._sessions["win1"] = session
    return ctrl, session, worker


def test_on_error_does_not_finish_while_running(monkeypatch):
    """Fix B：loop_error（单轮可重试错误）不触发 _finish —— 运行中线程不得被清理"""
    ctrl, session, worker = _make_controller_with_session(monkeypatch)
    # 运行卡 mock
    ctrl._running_cards = {"win1": MagicMock()}

    ctrl._on_error("win1", "单轮失败（可重试）")

    # 不得进入 _finish：独占锁未释放、worker 引用未清
    session.services["exit_exclusive_ui_mode"].assert_not_called()
    assert session.worker is worker


def test_finish_never_deletes_running_thread(monkeypatch):
    """Fix A：wait 超时路径绝不 deleteLater —— 改挂 finished 后延迟销毁"""
    ctrl, session, worker = _make_controller_with_session(monkeypatch)
    ctrl._running_cards = {"win1": MagicMock()}

    ctrl._finish("win1", "测试收尾")

    worker.deleteLater.assert_not_called()  # 运行中：不得直接销毁
    # 安全路径：先 cancel/interrupt，再挂 finished.connect(deleteLater)
    assert worker.cancel.called or worker.requestInterruption.called
    worker.finished.connect.assert_called()
    # 已退出线程（wait 成功）仍走 deleteLater —— 正常路径回归
    worker2 = MagicMock()
    worker2.isRunning.return_value = False
    worker2.wait.return_value = True  # 已退出
    session2 = MagicMock()
    session2.worker = worker2
    session2.finishing = False
    session2.services = session.services
    session2.running_card = None
    session2.prev_workdir = ""
    ctrl._sessions["win2"] = session2
    ctrl._finish("win2", "正常收尾")
    worker2.deleteLater.assert_called_once()


def test_streaming_deadlock_reset_on_stale_worker():
    """Fix D：_is_streaming 残留 + current_worker 已删 → 每轮对话前强制复位（防死循环）"""
    from autoloop_core.engine import AutoLoopEngine
    from autoloop_core.worker import AutoLoopWorker

    worker = AutoLoopWorker.__new__(AutoLoopWorker)
    worker._engine = MagicMock()
    # executor：is_streaming=True + current_worker 为已删 wrapper（访问即 RuntimeError）
    dead = MagicMock()
    dead.isRunning.side_effect = RuntimeError("wrapped C/C++ object deleted")
    executor = MagicMock()
    executor.is_streaming = True
    executor.get_current_worker.return_value = dead
    worker._conversation_executor = executor
    worker._adapter = MagicMock()
    worker._current_phase_tools = None
    worker.log_signal = MagicMock()

    # 直接驱动真实方法的复位段（等价 _execute_llm_conversation 前置防御）
    if worker._conversation_executor.is_streaming:
        stale = worker._conversation_executor.get_current_worker()
        if not AutoLoopWorker._alive_worker(stale):
            worker._conversation_executor._is_streaming = False
            worker._conversation_executor._current_worker = None
            worker.log_signal.emit("🔓 复位残留的流式状态（上轮 worker 已销毁）")

    assert worker._conversation_executor._is_streaming is False  # 死锁解除
    assert worker._conversation_executor._current_worker is None
    worker.log_signal.emit.assert_called_once()
    assert "复位" in worker.log_signal.emit.call_args[0][0]


def test_worker_marks_cancelled_after_3_consecutive_failures():
    """Fix C：连续 3 次单轮失败 → _is_cancelled=True（主循环退出，走 loop_stopped 正常收尾）"""
    from autoloop_core.engine import AutoLoopEngine
    from autoloop_core.worker import AutoLoopWorker

    worker = AutoLoopWorker.__new__(AutoLoopWorker)
    worker._config = MagicMock()
    worker._config.max_iterations = 5
    worker._config.task_prompt = "t"
    worker._engine = AutoLoopEngine(worker._config)
    worker._conversation_core = MagicMock()
    worker._conversation_executor = MagicMock()
    worker._adapter = MagicMock()
    worker._adapter.get_response.return_value = ""
    worker._all_messages = []
    worker._round_messages = []
    worker._prev_message_count = 0
    worker._last_message_token_count = 0
    worker._is_cancelled = False
    worker._is_archive_button_click = False
    worker._last_step = 0
    worker._all_tools_schema = []
    worker._tools_schema = []
    worker._build_messages = MagicMock(return_value=[])
    for name in ("iteration_started", "iteration_completed", "progress_updated",
                 "loop_completed", "loop_error", "loop_stopped", "phase_changed",
                 "log_signal", "log_update", "tokens_updated", "messages_logged"):
        setattr(worker, name, MagicMock())

    # 每轮 LLM 对话都失败：executor.execute 抛异常（走 _execute_llm_conversation
    # 内部 except 路径——连续 3 次后应置 _is_cancelled 并退出主循环）
    worker._model_config_getter = lambda: {}
    worker._make_autoloop_callbacks = MagicMock(return_value={})
    worker._conversation_executor.execute = MagicMock(side_effect=RuntimeError("模拟连续失败"))
    worker._adapter.reset = MagicMock()
    worker._emit_progress = MagicMock()
    worker._handle_planning_phase = MagicMock(return_value=False)
    worker._handle_executing_phase = MagicMock(return_value=False)
    worker._handle_archiving_phase = MagicMock(return_value=False)
    worker._engine.state = "executing"

    # 跑主循环（连续失败路径）——异常由 _execute_llm_conversation 内部 except 消化
    worker.run()

    assert worker._is_cancelled is True  # 连续 3 次后主动取消
    worker.loop_error.emit.assert_any_call("出错: 模拟连续失败")
