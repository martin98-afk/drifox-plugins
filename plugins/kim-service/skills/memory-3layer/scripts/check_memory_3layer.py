#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate the public Memory 3-Layer package without mutating it."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Iterable, List, Optional


REQUIRED = (
    "SKILL.md",
    "README.md",
    "README_CN.md",
    "LICENSE",
    "CHANGELOG.md",
    "NOTICE",
    "install.ps1",
    "install.sh",
    "hooks/hook_io.py",
    "hooks/memory_paths.py",
    "hooks/memory_store.py",
    "hooks/session_state.py",
    "hooks/memory_loader.py",
    "hooks/memory_extractor.py",
    "hooks/pre_compact.py",
    "scripts/install_memory_3layer.py",
    "scripts/migrate_legacy_memory.py",
    "scripts/record_memory.py",
    "scripts/check_memory_3layer.py",
    "evals/test_install_memory_3layer.py",
    "evals/test_migrate_legacy_memory.py",
    "evals/test_recording.py",
    "docs/images/contact-qr.png",
    "docs/images/wechat-pay.jpg",
    "docs/images/alipay.jpg",
)
FORBIDDEN_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "test-results",
    "outputs",
    "private",
    "research",
    "acceptance",
}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.I),
    re.compile(r"\b(?:sk|rk|pk)-(?:live-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}\b", re.I),
)
MACHINE_PATH_PATTERNS = (
    re.compile(r"\b[A-Za-z]:\\Users\\[^\\\s]+", re.I),
    re.compile(r"/(?:Users|home)/[^/\s]+/"),
)
TEXT_SUFFIXES = {".md", ".py", ".json", ".ps1", ".sh", ".txt", ".toml", ".yaml", ".yml"}
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def _is_reparse_or_symlink(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        info = os.lstat(path)
    except OSError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _iter_paths(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        yield path


def _read_text(path: Path, errors: List[str]) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        errors.append(f"unreadable UTF-8 text: {path.name}: {type(error).__name__}")
        return None


def _check_markdown_links(root: Path, path: Path, text: str, errors: List[str]) -> None:
    for raw_target in LINK_PATTERN.findall(text):
        target = raw_target.strip().strip("<>").split("#", 1)[0]
        if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):
            continue
        resolved = (path.parent / target).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            errors.append(f"local link escapes package: {path.relative_to(root).as_posix()} -> {target}")
            continue
        if not resolved.exists():
            errors.append(f"broken local link: {path.relative_to(root).as_posix()} -> {target}")


def check(root: Path) -> dict:
    root = Path(root).expanduser().resolve()
    errors: List[str] = []
    if not root.is_dir():
        return {"success": False, "root": str(root), "errors": ["package root is not a directory"]}

    for relative in REQUIRED:
        path = root / relative
        if not path.is_file() or _is_reparse_or_symlink(path):
            errors.append(f"missing or unsafe required file: {relative}")

    files: List[Path] = []
    for path in _iter_paths(root):
        relative = path.relative_to(root)
        if _is_reparse_or_symlink(path):
            errors.append(f"symlink/reparse point is forbidden: {relative.as_posix()}")
            continue
        if any(part in FORBIDDEN_PARTS for part in relative.parts):
            errors.append(f"forbidden package residue: {relative.as_posix()}")
        if path.is_file():
            files.append(path)

    skill_path = root / "SKILL.md"
    skill = _read_text(skill_path, errors) if skill_path.is_file() else None
    if skill is not None:
        lines = skill.splitlines()
        if len(lines) >= 500:
            errors.append(f"SKILL.md must be under 500 lines; found {len(lines)}")
        if not lines or lines[0].strip() != "---" or lines.count("---") < 2:
            errors.append("SKILL.md must start with YAML frontmatter")
        if not re.search(r"(?m)^name:\s*memory-3layer\s*$", skill):
            errors.append("SKILL.md frontmatter name must be memory-3layer")
        if not re.search(r"(?m)^description:\s*\S.+$", skill):
            errors.append("SKILL.md frontmatter needs a non-empty description")
        if re.search(r"(?m)^name:\s*claude-memory-3layer\s*$", skill):
            errors.append("legacy Claude-specific skill name is still active")

    for path in files:
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = _read_text(path, errors)
        if text is None:
            continue
        relative = path.relative_to(root).as_posix()
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"secret-like content: {relative}")
                break
        for pattern in MACHINE_PATH_PATTERNS:
            if pattern.search(text):
                errors.append(f"machine-specific path: {relative}")
                break
        if path.suffix.lower() == ".md":
            _check_markdown_links(root, path, text, errors)
        if path.suffix.lower() == ".py":
            try:
                compile(text, str(path), "exec")
            except SyntaxError as error:
                errors.append(f"Python syntax error: {relative}:{error.lineno}")

    for relative, expected_type in (
        ("templates/items.json", list),
        ("templates/session_state.json", dict),
    ):
        path = root / relative
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            errors.append(f"invalid JSON template: {relative}")
        else:
            if not isinstance(value, expected_type):
                errors.append(f"wrong JSON template type: {relative}")

    for readme_name in ("README.md", "README_CN.md"):
        path = root / readme_name
        text = _read_text(path, errors) if path.is_file() else ""
        if text:
            if not re.search(
                r'<p\s+align="center">\s*<img\s+src="docs/images/contact-qr\.png"\s+width="720"[^>]*>\s*</p>',
                text,
                re.S,
            ):
                errors.append(f"{readme_name} contact image must be centered at width 720")
            table = re.search(r'<table\s+align="center">(.*?)</table>', text, re.S)
            if not table:
                errors.append(f"{readme_name} payment images need one centered table")
            else:
                body = table.group(1)
                for image in ("wechat-pay.jpg", "alipay.jpg"):
                    if not re.search(
                        rf'<td\s+align="center">\s*<img\s+src="docs/images/{re.escape(image)}"\s+width="260"',
                        body,
                        re.S,
                    ):
                        errors.append(f"{readme_name} {image} must be in a centered width-260 cell")

    return {
        "success": not errors,
        "root": str(root),
        "file_count": len(files),
        "errors": errors,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv)
    report = check(Path(args.root))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
