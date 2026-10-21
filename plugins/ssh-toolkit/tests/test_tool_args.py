"""工具入参健壮性：模型把 integer 参数传成 None / 字符串不得炸。

背景：LLM 调用工具时偶发显式传 null 或把 integer 参数序列化成字符串，
``kwargs.get("port", 22)`` 的默认值只在 key 缺失时生效，key 存在而值为 None
时 ``int(None)`` 抛 ``TypeError: int() argument must be a string, a
bytes-like object or a real number, not 'NoneType'``。

隔离策略：同目录的 test_exec_bounded / test_forward_guard / test_transfer_guard
把 ``exec_tool`` / ``forward`` / ``transfer`` 当顶层模块 import（依赖 conftest
注入的 tools/ 与 vendored deps）。本文件不掺和那套，自行按文件路径把被测模块
装进 sys.modules，既拿到真实源码，也不与它们的 import 串味。
"""
import importlib.util
import os
import sys
import types

import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.join(os.path.dirname(_TESTS_DIR), "tools")


@pytest.fixture
def stub_app_result(monkeypatch):
    result = types.ModuleType("app.tools.result")

    class ToolResult:
        def __init__(self, success, content=None, error=None):
            self.success = success
            self.content = content
            self.error = error

    result.ToolResult = ToolResult
    monkeypatch.setitem(sys.modules, "app", types.ModuleType("app"))
    monkeypatch.setitem(sys.modules, "app.tools", types.ModuleType("app.tools"))
    monkeypatch.setitem(sys.modules, "app.tools.result", result)


def _load(monkeypatch, module_name, filename):
    """按文件路径加载 tools/ 下的被测模块，绕过 conftest 的 sys.path 注入。

    真实场景里这些模块也由宿主 PluginToolLoader 按路径加载，用 importlib
    直读文件与线上路径一致；同时避免 vendored deps 的 _rust.pyd 被拖进来
    （本机缺 VC++ runtime 导出符号）。
    """
    full = os.path.join(_TOOLS_DIR, filename)
    spec = importlib.util.spec_from_file_location(f"ssh_toolkit_{module_name}", full)
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, f"ssh_toolkit_{module_name}", mod)
    spec.loader.exec_module(mod)
    return mod
