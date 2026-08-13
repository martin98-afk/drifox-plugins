# -*- coding: utf-8 -*-
"""Load the three memory layers at SessionStart for Claude Code or Codex."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from hook_io import context_output, emit_json, read_hook_payload
from memory_paths import get_read_memory_dirs
from session_state import get_working_context


def _integer_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _normalized_fact(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def load_layer3_memory(read_dirs: Sequence[Path]) -> str:
    """Load the first available tacit-memory file (canonical wins)."""
    for root in read_dirs:
        memory_file = root / "MEMORY.md"
        try:
            content = memory_file.read_text(encoding="utf-8").strip()
        except (FileNotFoundError, OSError, UnicodeError):
            continue
        if content:
            return f"## Layer 3: Tacit knowledge\n{content}"
    return ""


def load_layer2_daily_notes(read_dirs: Sequence[Path]) -> str:
    """Load each recent date once, preferring the canonical copy."""
    days = _integer_env("MEMORY_DAILY_DAYS", 3, 0, 30)
    parts: List[str] = []
    for offset in range(days):
        date_string = (datetime.now() - timedelta(days=offset)).strftime("%Y-%m-%d")
        for root in read_dirs:
            note_file = root / "memory" / f"{date_string}.md"
            try:
                content = note_file.read_text(encoding="utf-8").strip()
            except (FileNotFoundError, OSError, UnicodeError):
                continue
            if content:
                parts.append(f"### {date_string}\n{content}")
                break
    return "## Layer 2: Recent notes\n\n" + "\n\n".join(parts) if parts else ""


def _read_topic_items(items_file: Path, warnings: Optional[List[str]] = None) -> List[Dict[str, object]]:
    try:
        value = json.loads(items_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError, UnicodeError):
        if warnings is not None:
            warnings.append(f"{items_file.parent.name}/items.json is unreadable or invalid; preserved and skipped")
        return []
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        if warnings is not None:
            warnings.append(f"{items_file.parent.name}/items.json has the wrong schema; preserved and skipped")
        return []
    return value


def load_layer1_knowledge_graph(read_dirs: Sequence[Path], warnings: Optional[List[str]] = None) -> str:
    """Merge active facts across roots without repeating legacy duplicates."""
    per_topic: Dict[str, List[Dict[str, object]]] = {}
    seen: Dict[str, set[str]] = {}
    for root in read_dirs:
        topics_dir = root / "areas" / "topics"
        if not topics_dir.is_dir():
            continue
        for topic_dir in sorted(topics_dir.iterdir(), key=lambda item: item.name):
            if not topic_dir.is_dir() or topic_dir.is_symlink():
                continue
            topic = topic_dir.name
            topic_seen = seen.setdefault(topic, set())
            for item in _read_topic_items(topic_dir / "items.json", warnings):
                if item.get("status", "active") != "active":
                    continue
                normalized = _normalized_fact(item.get("fact"))
                if not normalized or normalized in topic_seen:
                    continue
                topic_seen.add(normalized)
                per_topic.setdefault(topic, []).append(item)

    max_items = _integer_env("MEMORY_MAX_ITEMS", 10, 1, 100)
    parts: List[str] = []
    for topic in sorted(per_topic):
        items = sorted(per_topic[topic], key=lambda item: str(item.get("timestamp", "")))
        recent = items[-max_items:]
        lines = [f"### {topic} ({len(recent)} active)"]
        lines.extend(f"- {item.get('fact')}" for item in recent)
        parts.append("\n".join(lines))
    return "## Layer 1: Structured facts\n\n" + "\n\n".join(parts) if parts else ""


def load_memory_context() -> str:
    read_dirs = get_read_memory_dirs()
    warnings: List[str] = []
    layer1 = load_layer1_knowledge_graph(read_dirs, warnings)
    sections = [
        "## Memory warnings\n" + "\n".join(f"- {item}" for item in warnings) if warnings else "",
        load_layer3_memory(read_dirs),
        load_layer2_daily_notes(read_dirs),
        layer1,
        get_working_context(),
    ]
    sections = [section for section in sections if section]
    if not sections:
        return ""

    context = "# Memory 3-Layer context\n\n" + "\n\n".join(sections)
    limit = _integer_env("MEMORY_MAX_CONTEXT_CHARS", 9000, 1000, 9800)
    if len(context) > limit:
        suffix = "\n\n[Memory context truncated to configured character budget.]"
        context = context[: max(0, limit - len(suffix))].rstrip() + suffix
    return context


def main() -> None:
    read_hook_payload()  # Consume and validate the host envelope; no metadata is persisted.
    try:
        context = load_memory_context()
    except Exception as error:
        emit_json({"systemMessage": f"[Memory 3-Layer] load skipped: {type(error).__name__}"})
        return
    emit_json(context_output("SessionStart", context))


if __name__ == "__main__":
    main()
