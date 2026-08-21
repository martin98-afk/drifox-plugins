# -*- coding: utf-8 -*-
"""autoloop 经 services conversation_stack 构建执行栈（撤销 deep import 的行为等价验证）

worker.py 顶层 import 了 app.core.conversation.config / autoloop_core.adapter —— 主仓代码缺失；
用 importlib + sys.modules stub 注入绕过（与 test_autoloop_run_barrier.py 同模式，不动 conftest）。
"""

import ast
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "autoloop"
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

pytest.importorskip("PyQt5")


# ---- 桩 app.* 模块（让 worker.py + adapter.py 顶层 import 不抛） ----
def _stub_app_modules():
    """为 worker.py / adapter.py 依赖的 app.* 注入空壳模块，避免插件仓测试需主仓代码。

    即便其他 test_* 文件已 stub 过，本测试需要的形状（ConversationCore.create 可调用、
    PermissionStrategy.AUTO_ALLOW 可取值）覆盖更新——强制覆盖防 stub 漂移。
    同时设置 _autoloop_test_stub 标记，与 test_autoloop_run_barrier.py 兼容（避免互相覆盖）。
    """
    app_pkg = sys.modules.get("app")
    if app_pkg is None:
        app_pkg = types.ModuleType("app")
        app_pkg.__path__ = []
        sys.modules["app"] = app_pkg
    # 双标记：_autoloop_test_stub 与 run_barrier 兼容，_autoloop_stack_test_stub 自识别
    app_pkg._autoloop_test_stub = True
    app_pkg._autoloop_stack_test_stub = True

    app_core = sys.modules.get("app.core") or types.ModuleType("app.core")
    if not hasattr(app_core, "__path__"):
        app_core.__path__ = []
    sys.modules["app.core"] = app_core

    for sub in ("conversation", "chat_session", "token_estimator"):
        if f"app.core.{sub}" not in sys.modules:
            m = types.ModuleType(f"app.core.{sub}")
            m.__path__ = []
            sys.modules[f"app.core.{sub}"] = m

    conv = sys.modules.get("app.core.conversation")
    if conv is None or not hasattr(conv, "__path__"):
        conv = types.ModuleType("app.core.conversation")
        conv.__path__ = []
        sys.modules["app.core.conversation"] = conv

    conv_mod_config = sys.modules.get("app.core.conversation.config")
    if conv_mod_config is None:
        conv_mod_config = types.ModuleType("app.core.conversation.config")
        sys.modules["app.core.conversation.config"] = conv_mod_config
    conv_mod_config.ConversationConfig = MagicMock
    # 真实 PermissionStrategy 是 Enum 类；stub 用 MagicMock 实例并挂个 AUTO_ALLOW 让 worker 能 getattr
    _perm_strategy_instance = MagicMock()
    _perm_strategy_instance.AUTO_ALLOW = "AUTO_ALLOW"
    conv_mod_config.PermissionStrategy = _perm_strategy_instance
    conv_mod_config.filter_interactive_tools = MagicMock()

    conv_mod_core = sys.modules.get("app.core.conversation.core")
    if conv_mod_core is None:
        conv_mod_core = types.ModuleType("app.core.conversation.core")
        sys.modules["app.core.conversation.core"] = conv_mod_core
    # 真实 ConversationCore 是类，提供 .create() 类方法
    class _StubConversationCore:
        @staticmethod
        def create(**_kw):
            return MagicMock(name="conv_core_instance")

    conv_mod_core.ConversationCore = _StubConversationCore

    if "app.core.conversation.adapters" not in sys.modules:
        adapters_pkg = types.ModuleType("app.core.conversation.adapters")
        adapters_pkg.__path__ = []
        sys.modules["app.core.conversation.adapters"] = adapters_pkg
    if "app.core.conversation.adapters.base" not in sys.modules:
        adapter_base = types.ModuleType("app.core.conversation.adapters.base")
        adapter_base.BaseConversationAdapter = MagicMock
        sys.modules["app.core.conversation.adapters.base"] = adapter_base
    if "app.core.conversation.executor" not in sys.modules:
        conv_mod_exec = types.ModuleType("app.core.conversation.executor")
        conv_mod_exec.ConversationExecutor = MagicMock
        sys.modules["app.core.conversation.executor"] = conv_mod_exec


_stub_app_modules()

# ---- 顺序：先加载 adapter.py（worker.py 顶层导入依赖），再加载 worker.py ----
_ADAPTER_PATH = _PLUGIN_ROOT / "autoloop_core" / "adapter.py"
_WORKER_PATH = _PLUGIN_ROOT / "autoloop_core" / "worker.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# adapter.py 自身 import 链需要 adapters_pkg / base 已被 stub（已就绪）
adapter_module = _load("autoloop_core.adapter", _ADAPTER_PATH)
worker_module = _load("autoloop_core.worker", _WORKER_PATH)

AutoLoopWorker = worker_module.AutoLoopWorker
AutoLoopConversationAdapter = adapter_module.AutoLoopConversationAdapter


def _make_worker_bare():
    """仅填 configure() 必需字段；不走 Qt 信号。"""
    worker = AutoLoopWorker.__new__(AutoLoopWorker)
    worker._config = MagicMock()
    worker._model_config_getter = lambda: {}
    worker._tool_executor = MagicMock()
    worker._tools_schema = []
    worker._all_tools_schema = []
    worker._agent_system_prompt_getter = lambda _n: ""
    return worker


def test_worker_uses_injected_stack():
    """configure 传入 stack → ConversationCore/Executor 由 stack 产出（非 deep import）"""
    worker = _make_worker_bare()
    fake_core = MagicMock()
    fake_executor = MagicMock()

    class _Stack:
        @staticmethod
        def create_core(get_model_config=None, agent_manager=None, backend=None, session_manager=None):
            return fake_core

        @staticmethod
        def create_executor(core, config=None, tool_executor=None, agent_manager=None):
            return fake_executor

        @staticmethod
        def create_config(**_kw):
            return MagicMock()

    worker.configure(
        config=worker._config,
        model_config_getter=worker._model_config_getter,
        tool_executor=worker._tool_executor,
        tools_schema=[],
        agent_system_prompt_getter=worker._agent_system_prompt_getter,
        agent_manager=None,
        conversation_stack=_Stack(),
    )
    assert worker._conversation_core is fake_core
    assert worker._conversation_executor is fake_executor


def test_worker_fallback_uses_deep_import_when_stack_none():
    """configure 不传 stack → 回退到 ConversationCore.create / ConversationExecutor deep import"""
    worker = _make_worker_bare()
    worker.configure(
        config=worker._config,
        model_config_getter=worker._model_config_getter,
        tool_executor=worker._tool_executor,
        tools_schema=[],
        agent_system_prompt_getter=worker._agent_system_prompt_getter,
        agent_manager=None,
        # conversation_stack 未传 → 回退
    )
    # 无异常即视为成功：configure 完整跑完，且属性都被填
    assert worker._conversation_core is not None
    assert worker._conversation_executor is not None
    assert worker._adapter is not None


def test_worker_imports_no_conversation_core_module():
    """worker 模块级不再 from app.core.conversation.core import（deep import 撤除守卫）"""
    src = _WORKER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    leaked = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            lineno = getattr(node, "lineno", 0)
            # executor deep import 只允许在函数内（lineno > 100 表示 configure 内）
            if "app.core.conversation.core" in mod and lineno < 50:
                leaked.append(f"模块级 core import 残留: line={lineno} {mod}")
            if "app.core.conversation.executor" in mod and lineno < 100:
                leaked.append(f"executor 不应模块级导入: line={lineno} {mod}")
    assert not leaked, "残留: " + "; ".join(leaked)


def test_worker_imports_no_conversation_executor_module():
    """worker 模块级不再 from app.core.conversation import ConversationExecutor（deep import 撤除守卫）"""
    src = _WORKER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    leaked = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "app.core.conversation":
                names = [n.name for n in node.names]
                if "ConversationExecutor" in names:
                    leaked.append(f"模块级 ConversationExecutor 残留: line={getattr(node, 'lineno', 0)}")
    assert not leaked, "残留: " + "; ".join(leaked)


def test_adapter_uses_object_base_no_module_dep():
    """adapter 无非 TYPE_CHECKING 守卫的 app.core import（deep import 撤除守卫）"""
    src = _ADAPTER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)

    # 找出所有 if TYPE_CHECKING 块的范围（end_lineno），不在范围内的 ImportFrom 视为泄漏
    type_checking_ranges = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
                type_checking_ranges.append((node.lineno, node.end_lineno or node.lineno))

    def _in_guarded(lineno: int) -> bool:
        return any(start <= lineno <= end for start, end in type_checking_ranges)

    leaked = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            lineno = getattr(node, "lineno", 0)
            if mod.startswith("app.core") and not _in_guarded(lineno):
                leaked.append(f"非守卫内 app.core import 残留: line={lineno} {mod}")
    assert not leaked, "残留: " + "; ".join(leaked)


def test_adapter_constructible_without_base_class():
    """adapter 实例化不抛（基类 object，不调用 super(core, executor)）"""
    core = MagicMock()
    executor = MagicMock()
    adapter = AutoLoopConversationAdapter(core=core, executor=executor)
    assert adapter._core is core
    assert adapter._executor is executor
    assert adapter._worker_done_event is not None
