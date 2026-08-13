# -*- coding: utf-8 -*-
"""Persist a small recovery state before Claude Code or Codex compacts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from hook_io import emit_json, read_hook_payload
from session_state import load_state, save_state


ALLOWED_STATE_FIELDS = (
    "trigger",
)


def save_compact_state(payload: Dict[str, Any]) -> Dict[str, Any]:
    current = load_state()
    update: Dict[str, Any] = {
        "compact_saved_at": datetime.now(timezone.utc).isoformat(),
        "compact_count": int(current.get("compact_count", 0)) + 1,
    }
    for key in ALLOWED_STATE_FIELDS:
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)) and str(value).strip():
            update[key] = str(value)[:500]
    save_state(update)
    return update


def main() -> None:
    payload = read_hook_payload()
    try:
        save_compact_state(payload)
    except Exception as error:
        emit_json({"systemMessage": f"[Memory 3-Layer] compact state not saved: {type(error).__name__}"})
        return
    # Universal JSON field supported by both hosts for PreCompact.
    emit_json({"continue": True})


if __name__ == "__main__":
    main()
