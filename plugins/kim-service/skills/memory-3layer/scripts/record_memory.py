#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Record one user-confirmed fact through the platform-neutral core."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
HOOKS_ROOT = PACKAGE_ROOT / "hooks"
sys.path.insert(0, str(HOOKS_ROOT))

from memory_extractor import extract_and_save, extract_fact_from_payload  # noqa: E402
from memory_paths import detect_project_root, get_memory_dir, initialize_memory_tree  # noqa: E402


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--fact", required=True)
    parser.add_argument("--topic")
    args = parser.parse_args(argv)

    supplied = Path(args.project_dir).expanduser().resolve()
    if not supplied.is_dir():
        print(json.dumps({"success": False, "error": f"Project directory does not exist: {supplied}"}, ensure_ascii=False))
        return 1

    payload = {
        "host": "manual",
        "tool_name": "memory-record",
        "memory_fact": args.fact,
    }
    if args.topic:
        payload["memory_topic"] = args.topic

    fact, reason, _ = extract_fact_from_payload(payload)
    if not fact:
        print(json.dumps({"success": False, "error": reason or "invalid-fact"}, ensure_ascii=False, indent=2))
        return 1

    project = detect_project_root(supplied)
    os.chdir(project)
    memory_dir = get_memory_dir(project)
    initialize_memory_tree(memory_dir, PACKAGE_ROOT / "templates")

    try:
        report = extract_and_save(payload)
    except (OSError, ValueError) as error:
        print(json.dumps({"success": False, "error": str(error)}, ensure_ascii=False, indent=2))
        return 1

    rejected = not report["written"] and any(
        not str(reason).startswith("duplicate-") for reason in report["skipped"]
    )
    print(json.dumps({"success": not rejected, **report}, ensure_ascii=False, indent=2))
    return 1 if rejected else 0


if __name__ == "__main__":
    raise SystemExit(main())
