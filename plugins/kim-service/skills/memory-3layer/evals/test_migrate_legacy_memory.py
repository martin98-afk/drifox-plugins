#!/usr/bin/env python3
"""Contract tests for the standalone legacy-memory migrator."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "migrate_legacy_memory.py"
SPEC = importlib.util.spec_from_file_location("memory_3layer_migrator", MODULE_PATH)
assert SPEC and SPEC.loader
MIGRATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATOR)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def file_snapshot(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


class MigrationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source = self.base / "legacy"
        self.target = self.base / "target"
        self.source.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def seed_valid_source(self) -> None:
        write_text(self.source / "MEMORY.md", "# Stable knowledge\n\nUse pnpm.\n")
        write_text(self.source / "memory" / "2026-07-15.md", "# 2026-07-15\n\nMigrated.\n")
        write_text(
            self.source / "areas" / "topics" / "tooling" / "items.json",
            json.dumps([{"fact": "Use pnpm", "status": "active"}], ensure_ascii=False),
        )

    def test_success_copies_only_recognized_layers_and_preserves_source(self) -> None:
        self.seed_valid_source()
        write_text(self.source / "random.txt", "ignore me")
        write_text(self.source / "memory" / "notes.md", "not a dated daily note")
        write_text(self.source / "areas" / "topics" / "tooling" / "extra.json", "{}")
        before = file_snapshot(self.source)

        result = MIGRATOR.migrate(self.source, self.target)

        self.assertEqual(result["invalid"], [])
        self.assertEqual(result["conflict"], [])
        self.assertEqual(
            result["copied"],
            ["MEMORY.md", "memory/2026-07-15.md", "areas/topics/tooling/items.json"],
        )
        self.assertTrue((self.target / "MEMORY.md").is_file())
        self.assertTrue((self.target / "memory" / "2026-07-15.md").is_file())
        self.assertTrue((self.target / "areas" / "topics" / "tooling" / "items.json").is_file())
        self.assertFalse((self.target / "random.txt").exists())
        self.assertFalse((self.target / "memory" / "notes.md").exists())
        self.assertFalse((self.target / "areas" / "topics" / "tooling" / "extra.json").exists())
        self.assertEqual(json.loads((self.target / "data" / "session_state.json").read_text()), {})
        self.assertEqual(file_snapshot(self.source), before)

    def test_invalid_candidate_blocks_every_write(self) -> None:
        write_text(self.source / "MEMORY.md", "valid\n")
        write_text(self.source / "areas" / "topics" / "bad" / "items.json", "{bad json")

        result = MIGRATOR.migrate(self.source, self.target)

        self.assertTrue(any("invalid-json" in item for item in result["invalid"]))
        self.assertEqual(result["copied"], [])
        self.assertFalse(self.target.exists())

    def test_conflict_blocks_other_planned_files(self) -> None:
        write_text(self.source / "MEMORY.md", "new source value\n")
        write_text(self.source / "memory" / "2026-07-15.md", "new note\n")
        write_text(self.target / "MEMORY.md", "existing target value\n")
        before = file_snapshot(self.target)

        result = MIGRATOR.migrate(self.source, self.target)

        self.assertEqual(result["conflict"], ["MEMORY.md"])
        self.assertEqual(result["copied"], [])
        self.assertFalse((self.target / "memory" / "2026-07-15.md").exists())
        self.assertEqual(file_snapshot(self.target), before)

    def test_dry_run_reports_plan_but_writes_nothing(self) -> None:
        self.seed_valid_source()

        result = MIGRATOR.migrate(self.source, self.target, dry_run=True)

        self.assertEqual(len(result["copied"]), 3)
        self.assertEqual(result["invalid"], [])
        self.assertEqual(result["conflict"], [])
        self.assertFalse(self.target.exists())

    def test_second_run_is_idempotent(self) -> None:
        self.seed_valid_source()
        first = MIGRATOR.migrate(self.source, self.target)
        after_first = file_snapshot(self.target)

        second = MIGRATOR.migrate(self.source, self.target)

        self.assertEqual(len(first["copied"]), 3)
        self.assertEqual(second["copied"], [])
        self.assertEqual(
            second["skipped"],
            ["MEMORY.md", "memory/2026-07-15.md", "areas/topics/tooling/items.json"],
        )
        self.assertEqual(second["invalid"], [])
        self.assertEqual(second["conflict"], [])
        self.assertEqual(file_snapshot(self.target), after_first)

    def test_equal_or_nested_roots_are_rejected_without_writes(self) -> None:
        write_text(self.source / "MEMORY.md", "valid\n")
        with self.subTest("equal"):
            with self.assertRaisesRegex(ValueError, "must differ"):
                MIGRATOR.migrate(self.source, self.source)
        nested = self.source / "nested-target"
        with self.subTest("target nested in source"):
            with self.assertRaisesRegex(ValueError, "must not contain"):
                MIGRATOR.migrate(self.source, nested)
        self.assertFalse(nested.exists())

    def test_secret_or_private_machine_path_blocks_all_writes(self) -> None:
        cases = {
            "credential-fixture": "OPENAI_" + "API_KEY" + "=" + "sk-" + "abcdefghijklmnopqrstuvwxyz123456\n",
            "windows-path": "Workspace: C:" + chr(92) + "Users" + chr(92) + "example" + chr(92) + "private-project\n",
            "unix-path": "Workspace: /" + "home/example/private-project/file.txt\n",
        }
        for name, unsafe in cases.items():
            with self.subTest(name):
                source = self.base / f"source-{name}"
                target = self.base / f"target-{name}"
                write_text(source / "MEMORY.md", "safe candidate\n")
                write_text(source / "memory" / "2026-07-15.md", unsafe)

                result = MIGRATOR.migrate(source, target)

                self.assertEqual(result["copied"], [])
                self.assertTrue(result["invalid"])
                self.assertFalse(target.exists())

    def test_symlink_anywhere_in_source_is_rejected(self) -> None:
        write_text(self.source / "MEMORY.md", "valid\n")
        outside = self.base / "outside.md"
        write_text(outside, "external\n")
        link = self.source / "unrecognized-link.md"
        try:
            link.symlink_to(outside)
        except OSError as error:
            # Windows commonly denies symlink creation without Developer Mode.
            # Keep the enforcement path covered deterministically in that case.
            fake_link = self.source / "simulated-link.md"

            def simulated_scan(root: Path):
                if root == self.source.resolve():
                    return [fake_link], []
                return [], []

            with mock.patch.object(MIGRATOR, "_scan_symlinks", side_effect=simulated_scan):
                result = MIGRATOR.migrate(self.source, self.target)
            self.assertIsInstance(error, OSError)
        else:
            result = MIGRATOR.migrate(self.source, self.target)

        self.assertTrue(any("symlink-not-allowed" in item for item in result["invalid"]))
        self.assertEqual(result["copied"], [])
        self.assertFalse(self.target.exists())

    def test_invalid_existing_state_blocks_new_files(self) -> None:
        write_text(self.source / "MEMORY.md", "valid\n")
        write_text(self.target / "data" / "session_state.json", "[]\n")
        before = file_snapshot(self.target)

        result = MIGRATOR.migrate(self.source, self.target)

        self.assertIn("data/session_state.json:invalid-session-state-schema", result["invalid"])
        self.assertEqual(result["copied"], [])
        self.assertFalse((self.target / "MEMORY.md").exists())
        self.assertEqual(file_snapshot(self.target), before)

    def test_empty_or_unrecognized_source_is_invalid_and_zero_write(self) -> None:
        write_text(self.source / "random.txt", "not one of the three layers")

        result = MIGRATOR.migrate(self.source, self.target)

        self.assertIn("source:no-recognized-memory-files", result["invalid"])
        self.assertEqual(result["copied"], [])
        self.assertFalse(self.target.exists())

    def test_cli_rejects_paths_outside_project(self) -> None:
        project = self.base / "project"
        project.mkdir()
        outside = self.base / "outside"
        outside.mkdir()
        output = io.StringIO()
        with redirect_stdout(output):
            code = MIGRATOR.main(
                [
                    "--project-dir",
                    str(project),
                    "--source",
                    str(outside),
                    "--target",
                    str(project / ".memory-3layer"),
                ]
            )
        self.assertEqual(code, 1)
        report = json.loads(output.getvalue())
        self.assertIn("must stay inside", report["invalid"][0])
        self.assertFalse((project / ".memory-3layer").exists())


if __name__ == "__main__":
    unittest.main()
