# -*- coding: utf-8 -*-
"""冒烟：vendor SDK 链路验证（不连网：注册/分发/响应构造/CARD patch）"""
import inspect
import json
import sys

sys.path.insert(0, "plugins/gateway-feishu/deps")

from lark_oapi.core.json import JSON
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
import lark_oapi.ws.client as wsc

captured = {}


def on_msg(data):
    pass


def on_card(data):
    captured["value"] = data.event.action.value
    captured["chat_id"] = data.event.context.open_chat_id
    from lark_oapi.event.callback.model.p2_card_action_trigger import (
        P2CardActionTriggerResponse,
    )

    return P2CardActionTriggerResponse({"toast": {"type": "success", "content": "test"}})


h = (
    EventDispatcherHandler.builder("", "")
    .register_p2_im_message_receive_v1(on_msg)
    .register_p2_card_action_trigger(on_card)
    .build()
)

payload = json.dumps(
    {
        "schema": "2.0",
        "header": {"event_type": "card.action.trigger", "token": "", "event_id": "e1"},
        "event": {
            "operator": {"open_id": "ou_123"},
            "action": {"tag": "button", "value": {"drifox_cmd": "/model DeepSeek deepseek-chat"}},
            "context": {"open_chat_id": "oc_abc", "open_message_id": "om_1"},
        },
    }
).encode()

result = h._do_without_validation(payload)
print("分发结果:", JSON.marshal(result))
assert captured["value"]["drifox_cmd"] == "/model DeepSeek deepseek-chat", captured
assert captured["chat_id"] == "oc_abc"
print("回调数据解析: OK", captured)

# 验证 patch 后 ws client CARD 分支存在
src = inspect.getsource(wsc.Client._handle_data_frame)
assert "MessageType.CARD" in src and src.count("_do_without_validation") >= 2, "patch missing"
print("ws client CARD 分发 patch: OK")
