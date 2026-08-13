# -*- coding: utf-8 -*-
"""Shared stdin/stdout helpers for Claude Code and Codex command hooks."""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict


def read_hook_payload() -> Dict[str, Any]:
    """Read one JSON object from stdin; invalid or empty input becomes ``{}``."""
    if sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read()
    except (OSError, UnicodeError):
        return {}
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def emit_json(value: Dict[str, Any]) -> None:
    """Write exactly one compact JSON object to stdout."""
    sys.stdout.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def context_output(event_name: str, context: str) -> Dict[str, Any]:
    """Build the shared Claude/Codex context envelope."""
    if not context:
        return {}
    return {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": context,
        }
    }


def detect_host(payload: Dict[str, Any]) -> str:
    """Best-effort provenance label; never changes the output schema."""
    explicit = os.environ.get("MEMORY_HOST", "").strip().lower()
    if explicit in {"claude", "codex", "manual"}:
        return explicit
    for key in ("runtime", "host", "client"):
        value = str(payload.get(key, "")).lower()
        if "codex" in value:
            return "codex"
        if "claude" in value:
            return "claude"
    model = str(payload.get("model", "")).lower()
    if model.startswith(("gpt-", "o1", "o3", "o4", "codex")):
        return "codex"
    if "claude" in model:
        return "claude"
    return "manual"
