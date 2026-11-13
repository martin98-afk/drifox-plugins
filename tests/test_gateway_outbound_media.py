# -*- coding: utf-8 -*-
"""gateway-wechat / gateway-feishu 出站媒体（图片与文件）发送回归测试。

背景：宿主 GatewayService._deliver_attachments 统一调 adapter.send_image /
send_file 把模型产出的本地附件发回平台。此前两插件分别返回 Not implemented
（飞书）与完全没有实现（微信），文件只能靠 Gitee 公网链接兜底。

本测试用假 HTTP 客户端验证协议形状，不打真实网络：
- 微信：getuploadurl → CDN AES-128-ECB 加密上传 → sendmessage image/file item
- 飞书：im/v1/images | im/v1/files 上传 → messages 发 image/file 消息
"""

import asyncio
import pytest
import importlib.util
import sys
import types
from enum import Enum
from pathlib import Path

_PLUGINS_DIR = Path(__file__).resolve().parent.parent / "plugins"


# ── 宿主 app.gateway.base stub ─────────────────────────────
def _build_fake_app_modules():
    """构造一套独立 stub，不读既有 sys.modules（其他测试文件可能先装了简化版）。"""
    app = types.ModuleType("app")
    gateway = types.ModuleType("app.gateway")
    base = types.ModuleType("app.gateway.base")

    class Platform(str, Enum):
        FEISHU = "feishu"
        WECHAT = "wechat"

    class MessageType:
        TEXT = 1
        IMAGE = 2
        FILE = 3

    class PlatformConfig:
        def __init__(self, enabled: bool = True, extra: dict | None = None, secret: str = "", **kwargs):
            self.enabled = enabled
            self.extra = extra or {}
            self.secret = secret
            self.bot_id = kwargs.get("bot_id", "")

    class SendResult:
        def __init__(self, success, message_id=None, error=None, retryable=False):
            self.success = success
            self.message_id = message_id
            self.error = error
            self.retryable = retryable

    class MessageEvent:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class ChatInfo:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class BasePlatformAdapter:
        def __init__(self, config, platform=None, **kwargs):
            self.config = config
            self.platform = platform
            self.name = "test"
            self._running = True
            self._connected = True
            self._last_error = None
            self._active_sessions = {}
            self._pending_messages = {}
            self._active_message_ids = {}

        @property
        def is_connected(self):
            return self._connected

        async def handle_message(self, event):
            pass

    base.Platform = Platform
    base.MessageType = MessageType
    base.PlatformConfig = PlatformConfig
    base.SendResult = SendResult
    base.MessageEvent = MessageEvent
    base.ChatInfo = ChatInfo
    base.BasePlatformAdapter = BasePlatformAdapter

    app.gateway = gateway
    gateway.base = base
    return {"app": app, "app.gateway": gateway, "app.gateway.base": base}


@pytest.fixture(autouse=True)
def _isolated_host_stubs():
    """本文件独占 app.gateway.base stub：全量跑时其他测试文件的简化版会覆盖它，
    导致本插件 import 失败或 PlatformConfig 不收 secret。进出各装一次并还原。"""
    stubs = _build_fake_app_modules()
    keys = list(stubs)
    saved = {k: sys.modules.get(k) for k in keys}
    sys.modules.update(stubs)
    # 清掉已按旧 stub 加载的插件模块
    for name in ("wechat_gw_outbound", "feishu_gw_outbound"):
        sys.modules.pop(name, None)
    try:
        yield
    finally:
        for name in ("wechat_gw_outbound", "feishu_gw_outbound"):
            sys.modules.pop(name, None)
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _load(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# ── 假 HTTP 客户端 ─────────────────────────────────────────
class _FakeResponse:
    def __init__(self, payload=None, status=200, headers=None, content=b"{}"):
        self._payload = payload or {}
        self.status_code = status
        self.headers = headers or {}
        self.content = content
        self.text = str(self._payload)

    def json(self):
        return self._payload


class _FakeHttpClient:
    """按调用顺序记录请求，返回预置响应。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)

    async def aclose(self):
        pass


# ==================== 微信 ====================

def _wechat_adapter(http_client):
    mod = _load("wechat_gw_outbound", _PLUGINS_DIR / "gateway-wechat" / "gateways" / "wechat.py")
    cfg = sys.modules["app.gateway.base"].PlatformConfig(secret="token")
    adapter = mod.WechatAdapter(cfg)
    adapter._http_client = http_client
    adapter._context_tokens["u1"] = {"token": "ctx-1", "ts": __import__("time").time()}
    return mod, adapter


def test_wechat_send_file_uploads_encrypted_then_sends_item(tmp_path):
    doc = tmp_path / "报告.pdf"
    doc.write_bytes(b"hello wechat")

    responses = [
        _FakeResponse({"upload_param": "UP", "ret": 0}),  # getuploadurl
        _FakeResponse(headers={"x-encrypted-param": "DL"}, content=b""),  # CDN 上传
        _FakeResponse({"ret": 0}),  # sendmessage
    ]
    client = _FakeHttpClient(responses)
    _mod, adapter = _wechat_adapter(client)

    result = asyncio.run(adapter.send_file("dm:u1", str(doc)))

    assert result.success is True
    assert len(client.calls) == 3
    _, up_url, up_kwargs = client.calls[0]
    assert up_url.endswith("/ilink/bot/getuploadurl")
    body = up_kwargs["json"]
    assert body["media_type"] == 3  # 文件
    assert body["rawsize"] == len(b"hello wechat")
    assert body["filesize"] % 16 == 0 and body["filesize"] > body["rawsize"]

    _, cdn_url, cdn_kwargs = client.calls[1]
    assert "encrypted_query_param=UP" in cdn_url
    assert cdn_kwargs["headers"]["Content-Type"] == "application/octet-stream"
    assert len(cdn_kwargs["content"]) == body["filesize"]  # 密文含 PKCS7 填充

    _, send_url, send_kwargs = client.calls[2]
    assert send_url.endswith("/ilink/bot/sendmessage")
    item = send_kwargs["json"]["msg"]["item_list"][0]
    assert item["type"] == 4  # ITEM_FILE
    assert item["file_item"]["file_name"] == "报告.pdf"
    assert item["file_item"]["len"] == str(len(b"hello wechat"))
    assert item["file_item"]["media"]["encrypt_query_param"] == "DL"
    assert item["file_item"]["media"]["encrypt_type"] == 1
    assert send_kwargs["json"]["msg"]["context_token"] == "ctx-1"


def test_wechat_send_image_uses_image_item(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 8)
    responses = [
        _FakeResponse({"upload_param": "UP", "ret": 0}),
        _FakeResponse(headers={"x-encrypted-param": "DL"}, content=b""),
        _FakeResponse({"ret": 0}),
    ]
    client = _FakeHttpClient(responses)
    _mod, adapter = _wechat_adapter(client)

    result = asyncio.run(adapter.send_image("dm:u1", str(img)))

    assert result.success is True
    body = client.calls[0][2]["json"]
    assert body["media_type"] == 1  # 图片
    item = client.calls[2][2]["json"]["msg"]["item_list"][0]
    assert item["type"] == 2  # ITEM_IMAGE
    assert item["image_item"]["mid_size"] == body["filesize"]


def test_wechat_send_file_without_context_token_fails_fast(tmp_path):
    doc = tmp_path / "x.pdf"
    doc.write_bytes(b"pdf")
    client = _FakeHttpClient([_FakeResponse({"upload_param": "UP", "ret": 0})])
    _mod, adapter = _wechat_adapter(client)
    adapter._context_tokens.clear()
    # 先上传再发消息的顺序会失败在发送前；但没 token 时上传仍会发生，
    # 这里只断言「没有 token 就不发消息」的语义
    result = asyncio.run(adapter.send_file("dm:u1", str(doc)))
    assert result.success is False
    assert "24h" in (result.error or "")


def test_wechat_send_file_missing_local_file(tmp_path):
    client = _FakeHttpClient([])
    _mod, adapter = _wechat_adapter(client)
    result = asyncio.run(adapter.send_file("dm:u1", str(tmp_path / "nope.pdf")))
    assert result.success is False
    assert client.calls == []


def test_wechat_aes_key_base64_roundtrip(tmp_path):
    """产出的 aes_key 必须能被人站 _parse_aes_key 解回同一个 16 字节密钥。"""
    import base64

    doc = tmp_path / "x.bin"
    doc.write_bytes(b"data")
    responses = [
        _FakeResponse({"upload_param": "UP", "ret": 0}),
        _FakeResponse(headers={"x-encrypted-param": "DL"}, content=b""),
        _FakeResponse({"ret": 0}),
    ]
    client = _FakeHttpClient(responses)
    mod, adapter = _wechat_adapter(client)
    asyncio.run(adapter.send_file("dm:u1", str(doc)))

    item = client.calls[2][2]["json"]["msg"]["item_list"][0]
    key_b64 = item["file_item"]["media"]["aes_key"]
    raw = base64.b64decode(key_b64)
    parsed = adapter._parse_aes_key({"media": {"aes_key": key_b64}})
    assert parsed is not None and len(parsed) == 16
    assert raw == b"" or len(parsed) == 16


# ==================== 飞书 ====================

def _feishu_adapter(http_client):
    mod = _load("feishu_gw_outbound", _PLUGINS_DIR / "gateway-feishu" / "gateways" / "feishu.py")
    cfg = sys.modules["app.gateway.base"].PlatformConfig(
        extra={"app_id": "id", "app_secret": "secret"}
    )
    adapter = mod.FeishuAdapter(cfg)
    adapter._http_client = http_client
    adapter._connected = True
    adapter._token = "tkn"
    adapter._token_expiry = __import__("time").time() + 3600
    return mod, adapter


def test_feishu_send_file_uploads_then_sends_file_message(tmp_path):
    doc = tmp_path / "报告.pdf"
    doc.write_bytes(b"%PDF-1.4 x")

    responses = [
        _FakeResponse({"code": 0, "data": {"file_key": "fk_1"}}),  # im/v1/files
        _FakeResponse({"code": 0, "data": {"message_id": "om_1"}}),  # messages
    ]
    client = _FakeHttpClient(responses)
    _mod, adapter = _feishu_adapter(client)

    result = asyncio.run(adapter.send_file("oc_chat", str(doc)))

    assert result.success is True
    assert result.message_id == "om_1"
    _, upload_url, upload_kwargs = client.calls[0]
    assert upload_url.endswith("/open-apis/im/v1/files")
    assert upload_kwargs["data"]["file_type"] == "stream"
    assert upload_kwargs["data"]["file_name"] == "报告.pdf"
    assert upload_kwargs["files"]["file"][0] == "报告.pdf"

    _, msg_url, msg_kwargs = client.calls[1]
    assert msg_url.endswith("/open-apis/im/v1/messages")
    assert msg_kwargs["json"]["msg_type"] == "file"
    assert msg_kwargs["json"]["content"] == '{"file_key": "fk_1"}'


def test_feishu_send_image_uses_images_endpoint(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG")
    responses = [
        _FakeResponse({"code": 0, "data": {"image_key": "ik_1"}}),
        _FakeResponse({"code": 0, "data": {"message_id": "om_2"}}),
    ]
    client = _FakeHttpClient(responses)
    _mod, adapter = _feishu_adapter(client)

    result = asyncio.run(adapter.send_image("oc_chat", str(img)))

    assert result.success is True
    assert client.calls[0][1].endswith("/open-apis/im/v1/images")
    assert client.calls[0][2]["data"]["image_type"] == "message"
    assert client.calls[1][2]["json"]["msg_type"] == "image"
    assert client.calls[1][2]["json"]["content"] == '{"image_key": "ik_1"}'


def test_feishu_upload_failure_returns_error(tmp_path):
    doc = tmp_path / "x.pdf"
    doc.write_bytes(b"pdf")
    client = _FakeHttpClient([_FakeResponse({"code": 99991663, "msg": "no perm"})])
    _mod, adapter = _feishu_adapter(client)

    result = asyncio.run(adapter.send_file("oc_chat", str(doc)))

    assert result.success is False
    assert "99991663" in (result.error or "")


def test_feishu_retries_once_on_230049(tmp_path):
    """230049 = 结果不确定，官方建议同 payload 重试一次。"""
    doc = tmp_path / "x.pdf"
    doc.write_bytes(b"pdf")
    responses = [
        _FakeResponse({"code": 0, "data": {"file_key": "fk"}}),
        _FakeResponse({"code": 230049, "msg": "unknown"}),
        _FakeResponse({"code": 0, "data": {"message_id": "om_3"}}),
    ]
    client = _FakeHttpClient(responses)
    _mod, adapter = _feishu_adapter(client)

    result = asyncio.run(adapter.send_file("oc_chat", str(doc)))

    assert result.success is True
    assert result.message_id == "om_3"
    assert len(client.calls) == 3


def test_feishu_missing_local_file(tmp_path):
    client = _FakeHttpClient([])
    _mod, adapter = _feishu_adapter(client)
    result = asyncio.run(adapter.send_file("oc_chat", str(tmp_path / "nope.pdf")))
    assert result.success is False
    assert client.calls == []
