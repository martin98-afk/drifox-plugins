# -*- coding: utf-8 -*-
"""kim-service 插件 — prompt_optimizer hook 单元测试

插件目录名带连字符，与 DriFox 实际插件加载方式一致，
通过 importlib 从文件路径加载模块。
"""

import importlib.util
from pathlib import Path

_HOOK_PATH = (
    Path(__file__).resolve().parent.parent
    / "plugins"
    / "kim-service"
    / "hooks"
    / "prompt_optimizer.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "kim_service_prompt_optimizer", _HOOK_PATH
)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _call(message: str) -> str:
    return _MODULE.hook("UserPromptSubmit", {"message": message})


def test_skip_simple_response():
    assert _call("好的") == ""
    assert _call("ok") == ""


def test_skip_slash_command():
    assert _call("/help") == ""
    assert _call("/clear 会话") == ""


def test_skip_too_short_no_intent():
    assert _call("abc") == ""


def test_skip_empty():
    assert _call("") == ""
    assert _call(None) == ""


def test_trigger_normal_request():
    out = _call("帮我写一个用户登录功能")
    assert "📝 **原始输入**" in out
    assert "优化后的理解" in out
    assert "优化后的完整提示词" in out
    assert "帮我写一个用户登录功能" in out


def test_trigger_short_diagnostic():
    assert "原始输入" in _call("这个不行")
    assert "原始输入" in _call("报错了")


def test_trigger_long_complex():
    out = _call(
        "我需要实现一个完整的购物车系统，包括添加商品、修改数量、删除商品和结算功能"
    )
    assert "success_criteria" in out or "验收标准" in out


def test_user_input_safely_fenced():
    """用户输入含反引号/标题符号时安全包裹，不被渲染"""
    out = _call("# Files mentioned by the user:\n\n## codex-clipboard.png")
    assert "```text\n# Files mentioned by the user:" in out
