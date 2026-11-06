# -*- coding: utf-8 -*-
"""tools/file_tools.py 顶层 exec 加载回归测试（复刻 PluginToolLoader 加载方式）。

背景：宿主 PluginToolLoader._load_module 以顶层模块名 exec tools/*.py（无父包），
模块级相对导入（from ..ui.formats import ...）会抛
ImportError: attempted relative import with no known parent package，
导致 open_file/open_docx 自 v0.4.0 起从未注册成功。修复后运行时动态加载 formats。
"""
import importlib.util
import sys
import types
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]

# 桩宿主 app.tools.result，测试不依赖宿主仓库
_stub_result = types.ModuleType("app.tools.result")


class _StubToolResult:
    def __init__(self, success, content=None, **kw):
        self.success = success
        self.content = content


_stub_result.ToolResult = _StubToolResult
sys.modules.setdefault("app", types.ModuleType("app"))
sys.modules.setdefault("app.tools", types.ModuleType("app.tools"))
sys.modules["app.tools.result"] = _stub_result

spec = importlib.util.spec_from_file_location(
    "_plugin_tool_file-designer_file_tools", PLUGIN / "tools" / "file_tools.py"
)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def test_load_without_parent_package():
    """顶层 exec（无父包）加载成功即回归通过：不再使用相对导入。"""
    assert hasattr(mod, "register")
    assert callable(mod._open_file_impl)


def test_register_only_open_file():
    """注册清单只含 open_file：旧名 open_docx 已移除（v0.5.2）。"""
    registered = []


    class _FakeRegistry:
        def register(self, name, schema, **kw):
            registered.append(name)
            return True


    mod.register(_FakeRegistry())
    assert registered == ["open_file"]


def test_load_formats_dynamic():
    """动态加载 formats 注册表：8 个后缀齐全。"""
    formats = mod._load_formats()
    assert formats.SUPPORTED_SUFFIXES == (
        ".csv", ".docx", ".mermaid", ".mmd", ".pptx", ".xlsm", ".xlsx", ".xmind",
    )
    assert " / " in formats.suffix_label()


def test_impl_suffix_guard():
    """不支持的后缀在触 UI 前被拒。"""
    r = mod._open_file_impl(None, path=str(Path(__file__).resolve()))
    assert not r.success
    assert "仅支持" in r.content


def test_impl_reuses_ui_side_module():
    """UI 侧模块已在 sys.modules 时复用（单一状态源）。"""
    fake = types.ModuleType("ui_plugin_file_designer.formats")
    fake.SUPPORTED_SUFFIXES = (".docx",)
    fake.suffix_label = lambda: "Fake"
    sys.modules["ui_plugin_file_designer.formats"] = fake
    try:
        assert mod._load_formats() is fake
    finally:
        sys.modules.pop("ui_plugin_file_designer.formats", None)
