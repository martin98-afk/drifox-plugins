# -*- coding: utf-8 -*-
"""jimeng 工具对真实 CLI 的冒烟测试（需本机已装 dreamina CLI）。

不消耗额度：只调用不产生生成任务的命令（version / credit / list_tasks），
且都用「预期可能失败」的宽松断言——未登录也应给出可读错误而不是崩。

未装 CLI 时整组跳过。
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_PLUGIN_TOOLS = Path(__file__).resolve().parents[1] / "tools"


class _FakeToolResult:
    def __init__(self, success, content=None, error=None, **kw):
        self.success = success
        self.content = content
        self.error = error
        self.data = kw.get("data")
        self.artifacts = kw.get("artifacts")


@pytest.fixture(scope="module")
def jm():
    app_pkg = types.ModuleType("app")
    tools_pkg = types.ModuleType("app.tools")
    result_mod = types.ModuleType("app.tools.result")
    result_mod.ToolResult = _FakeToolResult
    registry_mod = types.ModuleType("app.tools.registry")
    registry_mod.make_summarize_from_preview = lambda preview: (
        lambda tool_name, tool_args, content: preview(tool_args)
    )
    sys.modules.setdefault("app", app_pkg)
    sys.modules.setdefault("app.tools", tools_pkg)
    sys.modules["app.tools.result"] = result_mod
    sys.modules["app.tools.registry"] = registry_mod

    spec = importlib.util.spec_from_file_location(
        "jimeng_tool_smoke", _PLUGIN_TOOLS / "jimeng.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not module._resolve_dreamina():
        pytest.skip("本机未安装 dreamina CLI")
    return module


def _ctx(tmp_path):
    return {"workdir": str(tmp_path), "env": {"app_data_dir": str(tmp_path)}}


def test_version(jm, tmp_path):
    res = jm._dispatch(_ctx(tmp_path), action="version")
    assert res.success, res.error
    assert "dreamina CLI" in res.content


def test_unknown_action(jm, tmp_path):
    res = jm._dispatch(_ctx(tmp_path), action="nope")
    assert not res.success
    assert "未知 action" in res.error


def test_credit_unlogged_gives_readable_error(jm, tmp_path):
    """未登录时应给引导语，不是原始栈或空错误。"""
    res = jm._dispatch(_ctx(tmp_path), action="credit")
    if res.success:
        assert res.content
    else:
        assert "login" in res.error.lower() or "登录" in res.error


def test_list_tasks_no_crash(jm, tmp_path):
    res = jm._dispatch(_ctx(tmp_path), action="list_tasks")
    assert res.success or res.error, "不应静默返回空"


def test_text2image_missing_prompt(jm, tmp_path):
    res = jm._dispatch(_ctx(tmp_path), action="text2image", resolution="2k")
    assert not res.success
    assert "prompt" in res.error


def test_upscale_missing_image(jm, tmp_path):
    res = jm._dispatch(_ctx(tmp_path), action="upscale", resolution="4k")
    assert not res.success
    assert "image" in res.error


def test_query_missing_submit_id(jm, tmp_path):
    res = jm._dispatch(_ctx(tmp_path), action="query")
    assert not res.success
    assert "submit_id" in res.error
