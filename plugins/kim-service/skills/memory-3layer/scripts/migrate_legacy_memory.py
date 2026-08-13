#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Explicit, non-destructive migration from legacy ``.claude/memory`` data."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


_UNIX_USER_ROOT = "(?:" + "Users" + "|" + "home" + ")"
_WINDOWS_USER_SEGMENT = "/" + "Users" + "/"
_FILE_SCHEME = "file" + ":///"
PRIVATE_PATH_PATTERNS = (
    re.compile(r"\b[A-Za-z]:[\\/][^\r\n\t\"'<>|]+", re.I),
    re.compile(r"(?:" + re.escape(_FILE_SCHEME) + r")?[A-Za-z]:" + re.escape(_WINDOWS_USER_SEGMENT) + r"[^/\s]+", re.I),
    re.compile(r"\\\\[^\\\s]+\\[^\\\s]+"),
    re.compile(r"/" + _UNIX_USER_ROOT + r"/[^/\s]+/"),
    re.compile(r"(?:^|[\s\"'])~[/\\]"),
)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.I),
    re.compile(r"\b(?:sk|rk|pk)-(?:live-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{16,}\b", re.I),
    re.compile(
        r"\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|cookie|session[_-]?token)"
        r"\s*[:=]\s*[\"']?\S{8,}",
        re.I,
    ),
)

DAILY_NOTE_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _validate_roots(source: Path, target: Path) -> None:
    source = source.resolve()
    target = target.resolve()
    if source == target:
        raise ValueError("source and target must differ")
    if _is_relative_to(source, target) or _is_relative_to(target, source):
        raise ValueError("source and target must not contain one another")


def _scan_symlinks(root: Path) -> Tuple[List[Path], List[Path]]:
    """Return symlinks and unreadable directories without following links."""

    if root.is_symlink():
        return [root], []
    if not root.is_dir():
        return [], []
    found: List[Path] = []
    unreadable: List[Path] = []
    pending = [root]
    while pending:
        current = pending.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            unreadable.append(current)
            continue
        for entry in entries:
            path = Path(entry.path)
            if entry.is_symlink():
                found.append(path)
            elif entry.is_dir(follow_symlinks=False):
                pending.append(path)
    key = lambda item: item.as_posix()
    return sorted(found, key=key), sorted(unreadable, key=key)


def _relative_or_name(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _recognized_files(source: Path) -> Iterable[Tuple[Path, Path]]:
    memory_file = source / "MEMORY.md"
    if memory_file.is_file() or memory_file.is_symlink():
        yield memory_file, Path("MEMORY.md")
    notes = source / "memory"
    if notes.is_dir():
        for path in sorted(notes.glob("*.md")):
            if DAILY_NOTE_NAME.fullmatch(path.name):
                yield path, Path("memory") / path.name
    topics = source / "areas" / "topics"
    if topics.is_dir():
        for path in sorted(topics.glob("*/items.json")):
            yield path, path.relative_to(source)


def _read_validated_content(path: Path, relative: Path) -> Tuple[Optional[str], Optional[bytes]]:
    if path.is_symlink():
        return "symlink-not-allowed", None
    try:
        payload = path.read_bytes()
        text = payload.decode("utf-8")
    except (OSError, UnicodeError):
        return "unreadable-utf8", None
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        return "sensitive-content", None
    if any(pattern.search(text) for pattern in PRIVATE_PATH_PATTERNS):
        return "private-machine-path", None
    if relative.name == "items.json":
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return "invalid-json", None
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            return "invalid-items-schema", None
    return None, payload


def _validate_target_state(target: Path) -> Optional[str]:
    state_file = target / "data" / "session_state.json"
    if not state_file.exists():
        return None
    problem, payload = _read_validated_content(state_file, Path("session_state.json"))
    if problem:
        return problem
    try:
        value = json.loads((payload or b"").decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return "invalid-json"
    return None if isinstance(value, dict) else "invalid-session-state-schema"


def _blocked_destination_parent(destination: Path, target: Path) -> Optional[Path]:
    current = destination.parent
    while current != target.parent:
        if current.exists() and not current.is_dir():
            return current
        if current == target:
            break
        current = current.parent
    return None


def migrate(source: Path, target: Path, *, dry_run: bool = False) -> Dict[str, List[str]]:
    source_input = Path(source).expanduser()
    target_input = Path(target).expanduser()
    result: Dict[str, List[str]] = {"copied": [], "skipped": [], "conflict": [], "invalid": []}
    if source_input.is_symlink():
        result["invalid"].append("source:symlink-not-allowed")
        return result
    if target_input.is_symlink():
        result["invalid"].append("target:symlink-not-allowed")
        return result
    source = source_input.resolve()
    target = target_input.resolve()
    _validate_roots(source, target)
    if not source.is_dir():
        result["invalid"].append("source:missing-directory")
        return result
    if target.exists() and not target.is_dir():
        result["invalid"].append("target:not-a-directory")
        return result

    source_links, source_unreadable = _scan_symlinks(source)
    for path in source_links:
        result["invalid"].append(f"source/{_relative_or_name(path, source)}:symlink-not-allowed")
    for path in source_unreadable:
        result["invalid"].append(f"source/{_relative_or_name(path, source)}:unreadable-directory")
    if target.exists():
        target_links, target_unreadable = _scan_symlinks(target)
        for path in target_links:
            result["invalid"].append(f"target/{_relative_or_name(path, target)}:symlink-not-allowed")
        for path in target_unreadable:
            result["invalid"].append(f"target/{_relative_or_name(path, target)}:unreadable-directory")

    candidates = list(_recognized_files(source))
    if not candidates:
        result["invalid"].append("source:no-recognized-memory-files")

    planned: List[Tuple[Path, bytes]] = []
    for path, relative in candidates:
        relative_text = relative.as_posix()
        problem, payload = _read_validated_content(path, relative)
        if problem:
            result["invalid"].append(f"{relative_text}:{problem}")
            continue
        destination = target / relative
        blocked_parent = _blocked_destination_parent(destination, target)
        if blocked_parent is not None:
            result["conflict"].append(f"{relative_text}:parent-not-directory")
            continue
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink() or not destination.is_file():
                result["conflict"].append(relative_text)
                continue
            try:
                identical = payload == destination.read_bytes()
            except OSError:
                identical = False
            result["skipped" if identical else "conflict"].append(relative_text)
            continue
        planned.append((relative, payload or b""))

    state_problem = _validate_target_state(target) if target.exists() else None
    if state_problem:
        result["invalid"].append(f"data/session_state.json:{state_problem}")

    # This is the write barrier: the complete source and destination preflight
    # above must pass before the target filesystem is touched.
    if result["invalid"] or result["conflict"]:
        return result

    if not dry_run:
        for relative, payload in planned:
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        (target / "memory").mkdir(parents=True, exist_ok=True)
        (target / "areas" / "topics").mkdir(parents=True, exist_ok=True)
        (target / "data").mkdir(parents=True, exist_ok=True)
        state_file = target / "data" / "session_state.json"
        if not state_file.exists():
            state_file.write_text("{}\n", encoding="utf-8")

    for relative, _payload in planned:
        result["copied"].append(relative.as_posix())
    return result


def _project_root(value: str) -> Path:
    # Keep the final path component lexical so migrate() can reject a symlink
    # passed explicitly via --source or --target before resolving it.
    return Path(os.path.abspath(Path(value).expanduser()))


def _inside_project(project: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(project.resolve())
        return True
    except ValueError:
        return False


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", default=".")
    parser.add_argument("--source")
    parser.add_argument("--target")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    project = _project_root(args.project_dir)
    source = _project_root(args.source) if args.source else project / ".claude" / "memory"
    target = _project_root(args.target) if args.target else project / ".memory-3layer"
    if not _inside_project(project, source) or not _inside_project(project, target):
        result = {
            "copied": [],
            "skipped": [],
            "conflict": [],
            "invalid": ["source and target must stay inside --project-dir"],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1
    try:
        result = migrate(source, target, dry_run=args.dry_run)
    except ValueError as error:
        result = {"copied": [], "skipped": [], "conflict": [], "invalid": [str(error)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["invalid"] or result["conflict"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
