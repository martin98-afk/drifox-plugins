# -*- coding: utf-8 -*-
"""@提及前缀剥离逻辑验证（与 feishu.py 内联实现同构）"""
import re
import sys

ok = True


def check(name, cond, detail=""):
    global ok
    if not cond:
        ok = False
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


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

check("群 @机器人 + 命令", process("@_user_1 /model", M) == "/model")
check("群 @机器人 + 对话", process("@_user_1 帮我查天气", M) == "帮我查天气")
check("@别人在前不误剥", process("@_user_2 @_user_1 /help", M) == "@马丁 @DriFox /help", process("@_user_2 @_user_1 /help", M))
check("命令 + @别人", process("/model @_user_2 看看", M) == "/model @马丁 看看")
check("普通文本不动", process("hello @_user_2 world", M) == "hello @马丁 world")
check("无 mentions 数组（防御剥）", process("@_user_1 /model", []) == "/model")
check("p2p 纯命令", process("/model", M) == "/model")
check("手打@不是占位符", process("@张三 你好", M) == "@张三 你好")

print("\n结果:", "全部通过 ✅" if ok else "存在失败 ❌")
sys.exit(0 if ok else 1)
