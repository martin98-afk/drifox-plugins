# -*- coding: utf-8 -*-
"""Session-state storage shared by all runtime adapters."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

from memory_paths import detect_project_root, get_state_file
from memory_store import atomic_write_json, file_lock, read_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> Dict[str, Any]:
    value = read_json(get_state_file(), {})
    return value if isinstance(value, dict) else {}


def save_state(state: Dict[str, Any]) -> None:
    state_file = get_state_file()
    with file_lock(state_file):
        current = read_json(state_file, {})
        merged = current if isinstance(current, dict) else {}
        merged.update(state)
        merged["last_updated"] = _now()
        atomic_write_json(state_file, merged)


def update_working_files(files: Iterable[str]) -> None:
    root = detect_project_root()
    incoming = []
    for item in files:
        value = str(item).strip()
        if not value:
            continue
        candidate = Path(value).expanduser()
        candidate = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            # Never persist project-external absolute paths from a hook payload.
            continue
        normalized = relative.as_posix()
        if normalized and normalized != ".":
            incoming.append(normalized[:500])
    if not incoming:
        return
    state_file = get_state_file()
    with file_lock(state_file):
        state = read_json(state_file, {})
        if not isinstance(state, dict):
            state = {}
        existing = state.get("working_files", [])
        if not isinstance(existing, list):
            existing = []
        state["working_files"] = list(dict.fromkeys(incoming + existing))[:20]
        state["last_updated"] = _now()
        atomic_write_json(state_file, state)


def set_current_task(task: str) -> None:
    task = str(task).strip()
    if task:
        save_state({"last_task": task[:500]})


def add_note(note: str) -> None:
    note = str(note).strip()
    if not note:
        return
    state_file = get_state_file()
    with file_lock(state_file):
        state = read_json(state_file, {})
        if not isinstance(state, dict):
            state = {}
        notes = state.get("notes", [])
        if not isinstance(notes, list):
            notes = [str(notes)] if notes else []
        notes.append(note[:500])
        state["notes"] = notes[-10:]
        state["last_updated"] = _now()
        atomic_write_json(state_file, state)


def get_working_context() -> str:
    state = load_state()
    if not state:
        return ""
    lines = ["## Session resume state"]
    if state.get("last_task"):
        lines.append(f"- Last task: {state['last_task']}")
    files = state.get("working_files")
    if isinstance(files, list) and files:
        lines.append(f"- Working files: {', '.join(str(item) for item in files[:5])}")
    notes = state.get("notes")
    if isinstance(notes, list):
        lines.extend(f"- Note: {item}" for item in notes[-3:])
    if state.get("compact_saved_at"):
        lines.append(f"- Last compact save: {state['compact_saved_at']}")
    return "\n".join(lines) if len(lines) > 1 else ""
