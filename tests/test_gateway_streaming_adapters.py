# -*- coding: utf-8 -*-
"""网关插件流式回复协议形状测试（telegram / discord / wecom / dingtalk / slack）。

宿主契约：``start_stream(chat_id) -> stream_key``、``update_stream(key, snapshot)``、
``finish_stream(key, final) -> SendResult``。这里用假 SDK / 假 HTTP 客户端验证
各平台发出的帧或 API 调用形状，不打真实网络。

加载方式：把 ``app.gateway.base`` 换成最小 stub 后按文件路径加载插件模块，
避免拉入宿主重量级依赖。
"""
import asyncio
import importlib.util
import sys
import types
from enum import Enum
from pathlib import Path

import pytest

from loguru import logger

_PLUGINS = Path(__file__).resolve().parent.parent / "plugins"


# ==================== 宿主 base stub ====================


class _Platform(str, Enum):
    TELEGRAM = "telegram"
    DISCORD = "discord"
    WECOM = "wecom"
    DINGTALK = "dingtalk"
    SLACK = "slack"


class _SendResult:
    def __init__(self, success, message_id=None, error=None, retryable=False):
        self.success = success
        self.message_id = message_id
        self.error = error
        self.retryable = retryable


class _BasePlatformAdapter:
    def __init__(self, config=None, platform=None, **kwargs):
        self.config = config
        self.platform = platform
        self._connected = False
        self._last_error = ""
        self._active_sessions = {}
        self._pending_messages = {}

    def supports_streaming(self, chat_id):
        return False

    async def start_stream(self, chat_id):
        return None

    async def update_stream(self, stream_key, snapshot):
        return False

    async def finish_stream(self, stream_key, final):
        return _SendResult(success=False, error="streaming not supported")

    def set_message_handler(self, handler):
        self._message_handler = handler


def _install_base_stub():
    if "app.gateway.base" in sys.modules and hasattr(
        sys.modules["app.gateway.base"], "_drfox_test_stub"
    ):
        return

    app = types.ModuleType("app")
    gateway = types.ModuleType("app.gateway")
    base = types.ModuleType("app.gateway.base")
    base._drfox_test_stub = True
    base.BasePlatformAdapter = _BasePlatformAdapter
    base.Platform = _Platform
    base.SendResult = _SendResult
    base.ChatInfo = type("ChatInfo", (), {})
    base.MessageEvent = type("MessageEvent", (), {})
    base.MessageType = type(
        "MessageType",
        (),
        {"TEXT": 1, "IMAGE": 2, "FILE": 3, "AUDIO": 4, "VIDEO": 5, "COMMAND": 6},
    )

    class _PlatformConfig:
        def __init__(self, **kwargs):
            self.enabled = kwargs.get("enabled", True)
            self.extra = kwargs.get("extra") or {}
            self.token = kwargs.get("token") or ""
            self.bot_id = kwargs.get("bot_id") or ""
            self.secret = kwargs.get("secret") or ""
            self.client_id = kwargs.get("client_id") or ""
            self.client_secret = kwargs.get("client_secret") or ""
            self.websocket_url = kwargs.get("websocket_url") or ""

    base.PlatformConfig = _PlatformConfig
    base.get_cache_dir = lambda name: Path("/tmp") / f"drifox-test-{name}"

    app.gateway = gateway
    gateway.base = base
    sys.modules["app"] = app
    sys.modules["app.gateway"] = gateway
    sys.modules["app.gateway.base"] = base


def _load(plugin: str, module_name: str):
    _install_base_stub()
    # 企微插件模块级 eager import aiohttp；测试只调流式协议，不需要真实实现
    if "aiohttp" not in sys.modules:
        sys.modules["aiohttp"] = types.ModuleType("aiohttp")
    if module_name in sys.modules:
        return sys.modules[module_name]
    path = _PLUGINS / plugin / "gateways" / f"{plugin.split('-')[-1]}.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _new(mod, cls_name, **attrs):
    obj = getattr(mod, cls_name).__new__(getattr(mod, cls_name))
    for key, value in attrs.items():
        setattr(obj, key, value)
    return obj


# ==================== telegram ====================


class _TgMessage:
    def __init__(self, message_id):
        self.message_id = message_id


class _TgBot:
    def __init__(self):
        self.sent = []
        self.edits = []
        self._next = 0

    async def send_message(self, **kwargs):
        self._next += 1
        self.sent.append(kwargs)
        return _TgMessage(self._next)

    async def edit_message_text(self, **kwargs):
        self.edits.append(kwargs)
        return True


def test_telegram_stream_edits_placeholder():
    mod = _load("gateway-telegram", "gw_telegram")
    bot = _TgBot()
    adapter = _new(mod, "TelegramAdapter", _bot=bot, _stream_states={})

    async def run():
        key = await adapter.start_stream("42")
        assert key == "tg:42:1"
        assert bot.sent[0]["text"] == "💭 正在思考…"
        assert await adapter.update_stream(key, "第一段")
        assert await adapter.update_stream(key, "第一段更长")  # 节流内，不重复编辑
        assert len(bot.edits) == 1
        result = await adapter.finish_stream(key, "最终答案")
        assert result.success is True
        return key

    key = asyncio.run(run())
    assert bot.edits[-1]["text"] == "最终答案"
    assert adapter._stream_states == {}


def test_telegram_stream_falls_back_without_bot():
    mod = _load("gateway-telegram", "gw_telegram")
    adapter = _new(mod, "TelegramAdapter", _bot=None, _stream_states={})
    assert adapter.supports_streaming("42") is False
    assert asyncio.run(adapter.start_stream("42")) is None


# ==================== discord ====================


class _DcMessage:
    def __init__(self, message_id):
        self.id = message_id
        self.edits = []

    async def edit(self, content):
        self.edits.append(content)


class _DcChannel:
    def __init__(self):
        self.sent = []
        self._next = 100

    async def send(self, content):
        self._next += 1
        msg = _DcMessage(self._next)
        self.sent.append((content, msg))
        return msg


class _DcClient:
    def __init__(self, channel):
        self.channel = channel

    def get_channel(self, chat_id):
        return self.channel


def test_discord_stream_edits_placeholder():
    mod = _load("gateway-discord", "gw_discord")
    channel = _DcChannel()
    adapter = _new(
        mod,
        "DiscordAdapter",
        _client=_DcClient(channel),
        _stream_states={},
    )

    async def run():
        key = await adapter.start_stream("123")
        assert key == "dc:123:101"
        assert channel.sent[0][0] == "💭 正在思考…"
        assert await adapter.update_stream(key, "第一段")
        assert await adapter.update_stream(key, "第一段更长")  # 节流内
        assert len(channel.sent[0][1].edits) == 1
        result = await adapter.finish_stream(key, "最终答案")
        assert result.success is True

    asyncio.run(run())
    assert channel.sent[0][1].edits[-1] == "最终答案"
    assert adapter._stream_states == {}


# ==================== wecom ====================


class _WcWs:
    closed = False

    def __init__(self):
        self.frames = []

    async def send_json(self, payload):
        self.frames.append(payload)


def test_wecom_stream_uses_respond_msg():
    mod = _load("gateway-wecom", "gw_wecom")
    ws = _WcWs()
    adapter = _new(
        mod,
        "WeComAdapter",
        _ws=ws,
        _reply_req_ids={"chat1": "req-1"},
        _stream_states={},
    )

    async def run():
        assert adapter.supports_streaming("chat1") is True
        key = await adapter.start_stream("chat1")
        assert key.startswith("wc:chat1:stream-")
        frame = ws.frames[0]
        assert frame["cmd"] == "aibot_respond_msg"
        assert frame["headers"]["req_id"] == "req-1"
        assert frame["body"]["msgtype"] == "stream"
        assert frame["body"]["stream"]["finish"] is False
        assert await adapter.update_stream(key, "第一段")
        assert await adapter.update_stream(key, "第一段更长")  # 2.5s 节流
        assert len(ws.frames) == 2
        result = await adapter.finish_stream(key, "最终答案")
        assert result.success is True

    asyncio.run(run())
    last = ws.frames[-1]["body"]["stream"]
    assert last["finish"] is True and last["content"] == "最终答案"
    assert adapter._stream_states == {}


def test_wecom_stream_requires_callback_req_id():
    mod = _load("gateway-wecom", "gw_wecom")
    adapter = _new(mod, "WeComAdapter", _ws=_WcWs(), _reply_req_ids={}, _stream_states={})
    assert adapter.supports_streaming("chat1") is False
    assert asyncio.run(adapter.start_stream("chat1")) is None


# ==================== dingtalk ====================


class _DdResponse:
    status_code = 200
    text = ""


class _DdHttp:
    def __init__(self):
        self.posts = []
        self.puts = []

    async def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return _DdResponse()

    async def put(self, url, **kwargs):
        self.puts.append((url, kwargs))
        return _DdResponse()


async def _fake_token():
    return "token"


def test_dingtalk_stream_creates_and_finalizes_ai_card():
    mod = _load("gateway-dingtalk", "gw_dingtalk")
    http = _DdHttp()
    adapter = _new(
        mod,
        "DingTalkAdapter",
        _http_client=http,
        _get_access_token=_fake_token,
        _chat_types={"chat1": "dm"},
        _client_id="robot",
        _stream_states={},
    )

    async def run():
        key = await adapter.start_stream("chat1")
        assert key.startswith("dd:chat1:drifox_")
        url, kwargs = http.posts[0]
        assert url.endswith("/v1.0/card/instances/createAndDeliver")
        assert kwargs["json"]["openSpaceId"] == "dtv1.card//IM_ROBOT.chat1"
        assert kwargs["json"]["cardData"]["cardParamMap"]["flowStatus"] == "2"
        assert await adapter.update_stream(key, "第一段")
        assert http.puts[0][0].endswith("/v1.0/card/streaming")
        assert http.puts[0][1]["json"]["isFinalize"] is False
        result = await adapter.finish_stream(key, "最终答案")
        assert result.success is True

    asyncio.run(run())
    assert http.puts[1][1]["json"]["isFinalize"] is True
    assert http.puts[-1][0].endswith("/v1.0/card/instances")
    assert http.puts[-1][1]["json"]["cardData"]["cardParamMap"]["flowStatus"] == "3"
    assert adapter._stream_states == {}


def test_dingtalk_stream_falls_back_when_card_rejected():
    mod = _load("gateway-dingtalk", "gw_dingtalk")

    class _RejectHttp(_DdHttp):
        async def post(self, url, **kwargs):
            self.posts.append((url, kwargs))
            return type("R", (), {"status_code": 403, "text": "no permission"})()

    adapter = _new(
        mod,
        "DingTalkAdapter",
        _http_client=_RejectHttp(),
        _get_access_token=_fake_token,
        _chat_types={"chat1": "group"},
        _client_id="robot",
        _stream_states={},
    )
    assert asyncio.run(adapter.start_stream("chat1")) is None


# ==================== slack ====================


class _SlClient:
    def __init__(self):
        self.calls = []
        self._next = 0

    def api_call(self, method, json=None):
        self.calls.append((method, json))
        if method == "chat.startStream":
            self._next += 1
            return {"ok": True, "ts": f"ts-{self._next}"}
        return {"ok": True}


def test_slack_stream_calls_official_methods():
    mod = _load("gateway-slack", "gw_slack")
    client = _SlClient()
    adapter = _new(mod, "SlackAdapter", _client=client, _stream_states={})

    async def run():
        key = await adapter.start_stream("C123")
        assert key == "sl:C123:ts-1"
        assert client.calls[0][0] == "chat.startStream"
        assert await adapter.update_stream(key, "第一段")
        assert client.calls[1][0] == "chat.appendStream"
        result = await adapter.finish_stream(key, "最终答案")
        assert result.success is True

    asyncio.run(run())
    assert client.calls[-1][0] == "chat.stopStream"
    assert client.calls[-1][1]["markdown_text"] == "最终答案"
    assert adapter._stream_states == {}


def test_slack_stream_falls_back_when_api_rejected():
    mod = _load("gateway-slack", "gw_slack")

    class _RejectClient(_SlClient):
        def api_call(self, method, json=None):
            raise RuntimeError("missing_scope")

    adapter = _new(mod, "SlackAdapter", _client=_RejectClient(), _stream_states={})
    assert asyncio.run(adapter.start_stream("C123")) is None
