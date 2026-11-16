"""微信 HTTP 200 业务错误不得被当成成功空轮询。"""

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from loguru import logger


@pytest.fixture
def adapter_type():
    # 只抽取真实网络/轮询方法，避免纯协议回归依赖宿主网关导入。
    path = Path(__file__).resolve().parents[1] / "plugins/gateway-wechat/gateways/wechat.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    methods = {"_api_post", "_is_session_expired", "_poll_once", "_poll_loop"}
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
               and any(getattr(method, "name", "") == "_poll_loop" for method in node.body))
    cls.bases = []
    cls.body = [method for method in cls.body if getattr(method, "name", "") in methods]
    namespace = {"asyncio": asyncio, "logger": logger, "Dict": dict, "Any": object,
                 "DEFAULT_API_BASE": "https://example.invalid", "REQUEST_TIMEOUT": 15,
                 "LONG_POLL_TIMEOUT": 45, "MAX_CONSECUTIVE_FAILURES": 3,
                 "BACKOFF_DELAYS": [0, 0, 0]}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[cls.name]


def make_adapter(adapter_type, payload):
    adapter = adapter_type()
    adapter._http_client = SimpleNamespace(post=AsyncMock(return_value=SimpleNamespace(
        status_code=200, json=lambda: payload)))
    adapter._api_headers = lambda: {}
    adapter._get_updates_buf = ""
    adapter._running = True
    adapter._connected = True
    adapter._last_error = ""
    adapter._save_cursor = lambda: None
    adapter._handle_inbound = lambda msg: None
    return adapter


@pytest.mark.parametrize("ret", [None, 0])
def test_expired_token_stops_after_one_request(adapter_type, ret):
    payload = {"errcode": -14, "errmsg": "expired"}
    if ret is not None:
        payload["ret"] = ret
    adapter = make_adapter(adapter_type, payload)

    async def run():
        # 旧代码不识别业务错误会忙轮询；第二次主动终止，避免测试自身挂死。
        response = adapter._http_client.post.return_value
        adapter._http_client.post.side_effect = [response, asyncio.CancelledError()]
        await adapter._poll_loop()

    asyncio.run(run())
    assert adapter._http_client.post.await_count == 1
    assert adapter._connected is False
    assert "已失效" in adapter._last_error


def test_non_expiry_business_error_is_reported(adapter_type):
    adapter = make_adapter(adapter_type, {"errcode": 123, "errmsg": "busy"})
    messages, expired, error = asyncio.run(adapter._poll_once())
    assert messages == []
    assert not expired
    assert isinstance(error, RuntimeError)


def test_success_without_ret_stays_supported(adapter_type):
    adapter = make_adapter(adapter_type, {"msgs": []})
    assert asyncio.run(adapter._poll_once()) == ([], False, None)
