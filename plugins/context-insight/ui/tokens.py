# -*- coding: utf-8 -*-
"""插件内令牌估算 —— 不依赖宿主主程序模块。

中文字符约 1.2 token/字，英文/代码/符号约 4 字符/token；与宿主快估口径一致。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

_CJK = re.compile(r"[\u4e00-\u9fff]")


def estimate_text(text: Any) -> int:
    if not text:
        return 0
    raw = text if isinstance(text, str) else str(text)
    if not raw:
        return 0
    cjk = len(_CJK.findall(raw))
    return max(1, int(cjk * 1.2 + (len(raw) - cjk) / 4.0))


def estimate_message(msg: Dict[str, Any]) -> int:
    if not isinstance(msg, dict):
        return 0
    total = 4 + estimate_text(msg.get("role", ""))
    total += estimate_text(_text_of(msg.get("content")))
    total += estimate_text(msg.get("reasoning_content"))
    for call in msg.get("tool_calls") or []:
        fn = call.get("function") if isinstance(call, dict) else None
        if isinstance(fn, dict):
            total += estimate_text(fn.get("arguments"))
    return total


def _text_of(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif isinstance(block.get("content"), str):
                    parts.append(block["content"])
        return "".join(parts)
    return str(content)


def count_tools(schema: List[Dict[str, Any]]) -> int:
    if not schema:
        return 0
    try:
        return estimate_text(json.dumps(schema, ensure_ascii=False))
    except Exception:
        return 0
