# -*- coding: utf-8 -*-
"""脱敏：诊断包内所有文本落盘前统一过一遍。

口径：
- 只掩盖「密钥形态」与「key: value 形态的凭据字段」，不动普通参数值
  （``max_tokens`` / ``token_budget`` 这类键不会命中，因为规则要求键后紧跟
  引号或冒号）。
- 路径、用户名、会话片段不脱敏（排查要用），由包内 README 明示风险。
"""
from __future__ import annotations

import re

REDACTED = "<已脱敏>"

_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # Authorization: Bearer xxx
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9\-._~+/]{8,}=*"), rf"\1 {REDACTED}"),
    # 各家 token 前缀
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{12,}"), f"sk-{REDACTED}"),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"), f"gh*_{REDACTED}"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"), f"xox-{REDACTED}"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), f"AKIA{REDACTED}"),
    (re.compile(r"\bAIza[0-9A-Za-z\-_]{30,}"), f"AIza{REDACTED}"),
    # key: value（JSON / ini / 日志行）
    (
        re.compile(
            r"(?i)((?:api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|"
            r"auth[_-]?token|id[_-]?token|client[_-]?secret|app[_-]?secret|"
            r"secret|password|passwd|authorization|cookie)"
            r"[\"']?\s*[:=]\s*[\"']?)([^\s\"',;}{]{4,})"
        ),
        rf"\1{REDACTED}",
    ),
)


def mask_text(text: str) -> tuple[str, int]:
    """返回 (脱敏后文本, 命中次数)。"""
    if not text:
        return text, 0
    hits = 0
    for pattern, repl in _RULES:
        text, n = pattern.subn(repl, text)
        hits += n
    return text, hits


def mask_bytes(data: bytes) -> tuple[bytes, int]:
    """按 UTF-8 解码后脱敏再编码；非法字节原样替换，不丢内容。"""
    text, hits = mask_text(data.decode("utf-8", errors="replace"))
    if not hits:
        return data, 0
    return text.encode("utf-8"), hits
