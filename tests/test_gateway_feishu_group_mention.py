# -*- coding: utf-8 -*-
"""飞书群聊响应策略回归（对齐 dsh-im 默认 mention 模式）。

群聊只在被 @机器人 时响应；``require_mention=False`` 才恢复「群内所有消息都响应」。
私聊不受影响。用最小假的 P2ImMessageReceiveV1 结构驱动 ``_on_feishu_message``。
"""
import asyncio
import json
import sys
import types
from enum import Enum
from pathlib import Path

import pytest

_PLUGIN_DIR = Path(__file__).resolve().parent.parent / "plugins" / "gateway-feishu"
_MODULE_NAME = "gw_feishu_group_mention"


def _install_fake_app_modules() -> None:
    if "app.gateway.base" in sys.modules:
        return
    app = types.ModuleType("app")
    gateway = types.ModuleType("app.gateway")
    base = types.ModuleType("app.gateway.base")

    class Platform(str, Enum):
        FEISHU = "feishu"

    class MessageType:
        TEXT = 1
        IMAGE = 2
        FILE = 3

    class PlatformConfig:
        def __init__(self, enabled=True, extra=None):
            self.enabled = enabled
            self.extra = extra or {}

    class SendResult:
        pass

    class MessageEvent:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class BasePlatformAdapter:
        def __init__(self, config, platform):
            self.config = config
            self.platform = platform
            self.name = "test"
            self._running = False
            self._connected = False
            self._last_error = None

        @property
        def is_connected(self):
            return self._connected

    base.Platform = Platform
    base.MessageType = MessageType
    base.PlatformConfig = PlatformConfig
    base.SendResult = SendResult
    base.MessageEvent = MessageEvent
    base.BasePlatformAdapter = BasePlatformAdapter
    base.get_cache_dir = lambda name: Path("/tmp") / f"drifox-test-{name}"

    app.gateway = gateway
    gateway.base = base
    sys.modules["app"] = app
    sys.modules["app.gateway"] = gateway
    sys.modules["app.gateway.base"] = base


def _load_feishu():
    _install_fake_app_modules()
    if _MODULE_NAME in sys.modules:
        return sys.modules[_MODULE_NAME]
    import importlib.util

    path = _PLUGIN_DIR / "gateways" / "feishu.py"
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = mod
    spec.loader.exec_module(mod)
    return mod


class _Obj:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeLoop:
    def is_running(self):
        return True


async def _noop(*args, **kwargs):
    return None


def _make_adapter(mod, require_mention=True):
    adapter = mod.FeishuAdapter.__new__(mod.FeishuAdapter)
    adapter._require_mention = require_mention
    adapter._handler_loop = _FakeLoop()
    adapter._message_handler = object()
    adapter._download_and_dispatch = _noop
    return adapter


def _make_data(chat_type="group", text="你好", mentions=None):
    message = _Obj(
        message_id="m1",
        chat_id="c1",
        chat_type=chat_type,
        message_type="text",
        content=json.dumps({"text": text}),
        mentions=mentions or [],
    )
    sender = _Obj(sender_id=_Obj(open_id="ou_1", user_id="", union_id=""))
    return _Obj(event=_Obj(message=message, sender=sender))


def _bot_mention(key="_user_1", name="drifox"):
    return _Obj(key=key, name=name, mentioned_type="app")


def _run_message(monkeypatch, mod, adapter, data):
    """调用 _on_feishu_message，返回被投递的协程数（1=已分发，0=被拦）。"""
    dispatched = []
    monkeypatch.setattr(
        mod.asyncio,
        "run_coroutine_threadsafe",
        lambda coro, loop: (dispatched.append(coro), coro.close()),
    )
    adapter._on_feishu_message(data)
    return len(dispatched)


def test_group_without_mention_is_skipped(monkeypatch):
    mod = _load_feishu()
    adapter = _make_adapter(mod, require_mention=True)
    assert _run_message(monkeypatch, mod, adapter, _make_data("group", "随便聊聊")) == 0


def test_group_with_bot_mention_dispatches(monkeypatch):
    mod = _load_feishu()
    adapter = _make_adapter(mod, require_mention=True)
    data = _make_data("group", "@_user_1 你好", [_bot_mention()])
    assert _run_message(monkeypatch, mod, adapter, data) == 1


def test_group_mention_disabled_accepts_all(monkeypatch):
    mod = _load_feishu()
    adapter = _make_adapter(mod, require_mention=False)
    assert _run_message(monkeypatch, mod, adapter, _make_data("group", "随便聊聊")) == 1


def test_dm_never_requires_mention(monkeypatch):
    mod = _load_feishu()
    adapter = _make_adapter(mod, require_mention=True)
    assert _run_message(monkeypatch, mod, adapter, _make_data("p2p", "你好")) == 1


def test_group_mention_of_other_bot_is_skipped(monkeypatch):
    """@ 的是别人（mentioned_type 非 app）不算对机器人说话。"""
    mod = _load_feishu()
    adapter = _make_adapter(mod, require_mention=True)
    other = _Obj(key="_user_1", name="张三", mentioned_type="user")
    data = _make_data("group", "@_user_1 你好", [other])
    assert _run_message(monkeypatch, mod, adapter, data) == 0


# ==================== 群消息留档 ====================


def _install_group_history_recorder(monkeypatch):
    calls = []

    class _Store:
        def capture(self, platform, chat_id, **kwargs):
            calls.append((platform, chat_id, kwargs))
            return True

    mod = types.ModuleType("app.gateway.group_history")
    mod.get_group_history_store = lambda: _Store()
    monkeypatch.setitem(sys.modules, "app.gateway.group_history", mod)
    return calls


def test_group_message_without_mention_is_archived(monkeypatch):
    """没 @机器人 的群消息也要留档，否则被叫住时看不到前文。"""
    mod = _load_feishu()
    adapter = _make_adapter(mod, require_mention=True)
    calls = _install_group_history_recorder(monkeypatch)
    assert _run_message(monkeypatch, mod, adapter, _make_data("group", "随便聊聊")) == 0
    platform, chat_id, kwargs = calls[0]
    assert (platform, chat_id) == ("feishu", "c1")
    assert kwargs["text"] == "随便聊聊"
    assert kwargs["chat_type"] == "group"
    assert kwargs["message_id"] == "m1"


def test_group_mention_text_is_archived_without_placeholder(monkeypatch):
    mod = _load_feishu()
    adapter = _make_adapter(mod, require_mention=True)
    calls = _install_group_history_recorder(monkeypatch)
    data = _make_data("group", "@_user_1 帮我看下", [_bot_mention()])
    assert _run_message(monkeypatch, mod, adapter, data) == 1
    assert calls[0][2]["text"] == "帮我看下"


def test_dm_is_not_archived(monkeypatch):
    mod = _load_feishu()
    adapter = _make_adapter(mod, require_mention=True)
    calls = _install_group_history_recorder(monkeypatch)
    assert _run_message(monkeypatch, mod, adapter, _make_data("p2p", "你好")) == 1
    assert calls == []
