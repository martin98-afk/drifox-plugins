# -*- coding: utf-8 -*-
"""Path policy for the platform-neutral three-layer memory core.

New writes always target ``MEMORY_DIR`` or ``<project>/.memory-3layer``.
The old ``<project>/.claude/memory`` directory is exposed only as an opt-in
read source. Migration is handled by the explicit migration tool.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from typing import List, Optional


DEFAULT_DIRECTORY_NAME = ".memory-3layer"
LEGACY_RELATIVE_PATH = Path(".claude") / "memory"


def _is_reparse_or_symlink(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        info = os.lstat(path)
    except OSError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _ensure_project_local(root: Path, path: Path) -> Path:
    root = root.resolve()
    path = path.resolve()
    if path == root:
        raise ValueError("MEMORY_DIR must not be the project root")
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ValueError("MEMORY_DIR must stay inside the project root") from error
    current = root
    for part in relative.parts:
        current = current / part
        if current.exists() and _is_reparse_or_symlink(current):
            raise ValueError(f"MEMORY_DIR crosses a symlink or reparse point: {current}")
    return path


def detect_project_root(cwd: Optional[Path] = None) -> Path:
    """Return the containing Git root, or the supplied/current directory."""
    base = Path(cwd or Path.cwd()).expanduser().resolve()
    try:
        result = subprocess.run(
            ["git", "-C", str(base), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
        if result.returncode == 0 and result.stdout and result.stdout.strip():
            return Path(result.stdout.strip()).resolve()
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        pass
    return base


def get_memory_dir(project_root: Optional[Path] = None) -> Path:
    """Resolve the only writable memory directory.

    A relative ``MEMORY_DIR`` is resolved from the detected project root so a
    hook behaves consistently when the host starts in a nested directory.
    """
    root = detect_project_root(project_root)
    configured = os.environ.get("MEMORY_DIR", "").strip()
    if not configured:
        return _ensure_project_local(root, root / DEFAULT_DIRECTORY_NAME)
    path = Path(configured).expanduser()
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    return _ensure_project_local(root, resolved)


def get_legacy_memory_dir(project_root: Optional[Path] = None) -> Path:
    """Return the legacy read-only memory directory."""
    return detect_project_root(project_root) / LEGACY_RELATIVE_PATH


def get_read_memory_dirs(project_root: Optional[Path] = None) -> List[Path]:
    """Return canonical reads plus an explicitly enabled legacy fallback."""
    primary = get_memory_dir(project_root)
    roots = [primary]
    # Legacy reads are opt-in.  This prevents a newly installed system from
    # silently depending forever on a host-specific directory.
    legacy_enabled = os.environ.get("MEMORY_LEGACY_READ", "0").lower()
    if legacy_enabled not in {"0", "false", "no", "off"}:
        legacy = get_legacy_memory_dir(project_root)
        if legacy != primary and legacy.exists():
            roots.append(legacy)
    return roots


def get_state_file(project_root: Optional[Path] = None) -> Path:
    """Return the session-state file under the writable memory root."""
    return get_memory_dir(project_root) / "data" / "session_state.json"


def initialize_memory_tree(memory_dir: Path, template_dir: Optional[Path] = None) -> None:
    """Create the minimum deterministic directory tree without overwriting data."""
    memory_dir = Path(memory_dir)
    (memory_dir / "memory").mkdir(parents=True, exist_ok=True)
    (memory_dir / "areas" / "topics").mkdir(parents=True, exist_ok=True)
    (memory_dir / "data").mkdir(parents=True, exist_ok=True)

    memory_file = memory_dir / "MEMORY.md"
    if not memory_file.exists():
        template = Path(template_dir) / "MEMORY.md" if template_dir else None
        if template and template.is_file():
            memory_file.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            memory_file.write_text("# Project Memory\n", encoding="utf-8")

    state_file = memory_dir / "data" / "session_state.json"
    if not state_file.exists():
        state_file.write_text("{}\n", encoding="utf-8")
