# -*- coding: utf-8 -*-
"""@提及前缀剥离逻辑验证（与 feishu.py 内联实现同构）

pytest 规范：断言全部在 test_* 函数内，不再使用脚本式 sys.exit。
Run: python -m pytest tests/test_feishu_mention_strip.py -v
"""
import re


def process(text: str, mentions: list) -> str:
    bot_keys = {m["key"] for m in mentions if m.get("key") and m.get("mentioned_type") == "app"}
    name_by_key = {m["key"]: f"@{m['name']}" for m in mentions if m.get("key")}
    lead = re.match(r"^(@_user_\d+)\s*", text)
    if lead and (not mentions or lead.group(1) in bot_keys):
        text = text[lead.end():]
    if name_by_key:
        text = re.sub(r"@\S+", lambda mm: name_by_key.get(mm.group(0), mm.group(0)), text)
    return text.strip()


BOT = {"key": "@_user_1", "name": "DriFox", "mentioned_type": "app"}
HUMAN = {"key": "@_user_2", "name": "马丁", "mentioned_type": "user"}
M = [BOT, HUMAN]


def test_bot_prefix_stripped():
    assert process("@_user_1 /model", M) == "/model"
    assert process("@_user_1 帮我查天气", M) == "帮我查天气"


def test_other_mention_prefix_not_stripped():
    got = process("@_user_2 @_user_1 /help", M)
    assert got == "@马丁 @DriFox /help", got


def test_command_with_trailing_mention():
    assert process("/model @_user_2 看看", M) == "/model @马丁 看看"


def test_plain_text_rewrites_names_only():
    assert process("hello @_user_2 world", M) == "hello @马丁 world"


def test_empty_mentions_still_strips_bot_placeholder():
    assert process("@_user_1 /model", []) == "/model"


def test_p2p_pure_command():
    assert process("/model", M) == "/model"


def test_handwritten_at_is_not_placeholder():
    assert process("@张三 你好", M) == "@张三 你好"
