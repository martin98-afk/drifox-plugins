# -*- coding: utf-8 -*-
"""ip-switcher monkey patch 单元测试"""
import sys
import types
from unittest.mock import MagicMock, patch

from ip_switcher_redirect import (
    _is_rate_limit_error,
    _is_whitelisted,
)


class _FakeRateLimit(Exception):
    """模拟 openai.RateLimitError（无 openai 时用）"""
    status_code = 429
    message = "rate limit exceeded"


def _fake_openai_module():
    """构造最小 openai 假模块"""
    m = types.ModuleType("openai")
    m.RateLimitError = _FakeRateLimit
    m.OpenAI = type("OpenAI", (), {"__init__": lambda self, *a, **k: None})
    m.AsyncOpenAI = type("AsyncOpenAI", (), {"__init__": lambda self, *a, **k: None})
    # chat.completions 层级
    comp = type("Completions", (), {
        "create": lambda self, *a, **k: None,
        "acreate": lambda self, *a, **k: None,
    })
    chat = type("chat", (), {"completions": comp()})
    m.chat = chat()
    return m


def test_is_rate_limit_error_429():
    err = _FakeRateLimit()
    assert _is_rate_limit_error(err) is True


def test_is_rate_limit_error_text():
    class E(Exception):
        message = "Quota exceeded for this IP"

    assert _is_rate_limit_error(E()) is True


def test_is_rate_limit_error_other():
    assert _is_rate_limit_error(ValueError("bad request")) is False


def test_is_whitelisted_model():
    with patch("ip_switcher_redirect.get_config") as mock_cfg:
        cfg = MagicMock()
        cfg.is_whitelisted_model.return_value = True
        cfg.is_whitelisted_base_url.return_value = False
        mock_cfg.return_value = cfg
        assert _is_whitelisted(model="free-gpt4o") is True