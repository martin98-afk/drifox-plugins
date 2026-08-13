#!/usr/bin/env python3
"""Create a cross-platform, fail-closed acceptance run workspace.

This command prepares files only. It never invokes a model, loads a skill,
assigns scores, or produces a release decision. Every generated status remains
pending until external host/reviewer attestations close the evidence boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PENDING_INPUT = "PENDING: replace with the exact original user input before either clean-session run."


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write(path: Path, content: str) -> None:
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare a pending acceptance/baseline folder without fabricating execution or scores."
    )
    parser.add_argument("legacy_date", nargs="?", help="Compatibility date in YYYY-MM-DD form")
    parser.add_argument("--mode", choices=["acceptance", "baseline", "regression"], default="acceptance")
    parser.add_argument("--date", dest="run_date", help="Run date used in the folder name")
    parser.add_argument("--run-id", help="Filesystem-safe run id; defaults to timestamped id")
    parser.add_argument("--input-file", type=Path, help="File containing the exact original user input")
    parser.add_argument("--output-root", type=Path, default=Path("test-results"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    run_date = args.run_date or args.legacy_date or date.today().isoformat()
    try:
        date.fromisoformat(run_date)
    except ValueError:
        print(f"invalid run date: {run_date}; expected YYYY-MM-DD", file=sys.stderr)
        return 2

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = args.run_id or f"meta-skill-creator-{args.mode}-{timestamp}"
    if not all(char.isalnum() or char in "._-" for char in run_id) or len(run_id) < 8:
        print("run id must contain only letters, digits, dot, underscore, or hyphen", file=sys.stderr)
        return 2

    input_text = PENDING_INPUT
    if args.input_file:
        input_text = args.input_file.read_text(encoding="utf-8").strip()
        if not input_text:
            print("input file is empty", file=sys.stderr)
            return 2

    run_dir = (args.output_root / f"{run_date}-meta-skill-creator-{args.mode}").resolve()
    if run_dir.exists():
        print(f"refusing to overwrite existing run folder: {run_dir}", file=sys.stderr)
        return 1
    run_dir.mkdir(parents=True)

    host_attestation_ref = f"../attestations/{run_id}-host-attestation.json"
    reviewer_attestation_ref = f"../attestations/{run_id}-reviewer-attestation.json"

    write(run_dir / "input.md", input_text)
    write(run_dir / "prompt-without-skill.txt", input_text)
    write(run_dir / "prompt-with-skill.txt", input_text)
    write(
        run_dir / "evidence-sweep.md",
        """# Evidence sweep

Status: pending
User material: PENDING: record what the user supplied.
Local / Graphify: PENDING: record exact local paths or graph queries read.
Official / platform: PENDING: record exact official sources or state unavailable.
High-signal: PENDING: record exact high-signal sources or state unavailable.
Counterevidence: PENDING: record contradictions and limits.
Evidence checked at: PENDING: ISO-8601 timestamp.
Evidence refs: PENDING: concrete paths or URLs used for the decision.
""",
    )
    write(
        run_dir / "tool-capability.md",
        """# Tool capability record

Status: pending
Checked at: PENDING: ISO-8601 timestamp.
Host runtime: PENDING: actual host and version.
Python command: PENDING: command that ran locally.
Skill invocation surface: PENDING: how the host loaded the skill.
Host attestation: PENDING: ../attestations/<run-id>-host-attestation.json.
Evidence refs: PENDING: runtime-without-skill.log; runtime-with-skill.log.
Limitations: PENDING: unavailable or unverified capability boundaries.
""",
    )
    write(
        run_dir / "scoring-rubric.md",
        """# Scoring rubric

Status: pending
Rubric ID: PENDING: stable rubric identifier.
Rubric frozen at: PENDING: ISO-8601 timestamp before either route starts.
Machine rubric: scoring-rubric.json
Scoring rule: each dimension is scored from zero to its weight; totals are recomputed.

Define observable criteria and weights in scoring-rubric.json before either route.
Do not copy totals from scripts or prior runs.
""",
    )
    (run_dir / "scoring-rubric.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "rubric_id": "pending-rubric-id",
                "frozen_at": None,
                "total_weight": 100,
                "dimensions": [
                    {
                        "id": "pending-dimension",
                        "weight": 100,
                        "criterion": "PENDING: replace with observable, route-comparable evidence.",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    write(
        run_dir / "without-skill-output.md",
        """# Without-skill output

Status: pending
Replace this file with the unedited output captured from the clean session that
did not load meta-skill-creator. Do not summarize or reconstruct the output.
""",
    )
    write(
        run_dir / "with-skill-output.md",
        """# With-skill output

Status: pending
Replace this file with the unedited output captured from the clean session that
loaded meta-skill-creator. A completed output must expose its Domain Research Brief,
Evidence sweep, Skillization Decision, Deep Research Decision, Goal Contract,
Execution Contract, and Boundary Contract rather than claim them here.
""",
    )
    write(
        run_dir / "runtime-without-skill.log",
        """Status: pending
Capture external host evidence for route=without-skill. The final log must contain
the host session id, route name, timestamps, result, prompt/output SHA-256. This
run-folder copy is artifact evidence only; the external host anchor is authoritative.
""",
    )
    write(
        run_dir / "runtime-with-skill.log",
        """Status: pending
Capture external host evidence for route=with-skill. The final log must contain
the host session id, trigger/load observation, timestamps, result, prompt/output
SHA-256. This run-folder copy is artifact evidence only.
""",
    )
    write(
        run_dir / "reviewer-notes.md",
        """# Reviewer notes

Reviewer: PENDING: independent reviewer identity.
Reviewer ID: PENDING: stable human reviewer id.
Reviewer type: PENDING: human.
Reviewed at: PENDING: ISO-8601 timestamp.
Reviewer attestation: PENDING: ../attestations/<run-id>-reviewer-attestation.json.
Rubric SHA-256: PENDING: scoring-rubric.json SHA-256.
Score summary:
Without-skill: PENDING: integer 0-100.
With-skill: PENDING: integer 0-100.
Delta: PENDING: with minus without.
Pass / partial / fail: PENDING: evidence-based decision.
Human status: PENDING: accepted or rejected.

Notes:
- PENDING: external attestation must score every rubric dimension and cite both outputs.
""",
    )
    write(
        run_dir / "release-gate.md",
        """# Release gate

Structure status: pending
Runtime status: pending
Human status: pending
Ready decision: pending
Release decided at: PENDING: ISO-8601 timestamp after review.
Host attestation SHA-256: PENDING: external host attestation hash.
Reviewer attestation SHA-256: PENDING: external reviewer attestation hash.
Rubric SHA-256: PENDING: scoring-rubric.json hash.

The preparation command cannot change these values. Local files can reach only
artifact_consistent. Runtime/human become verified only from external attestations.
""",
    )
    write(
        run_dir / "validation.md",
        """# Validation record

Validation command: PENDING: exact commands executed.
Validation status: pending
Validation run at: PENDING: ISO-8601 timestamp.
Result evidence: validation.log
Validation log SHA-256: PENDING: hash of validation.log.

Record structure/package checks here. The acceptance validator independently
recomputes hashes and evidence closure; this file cannot self-certify readiness.
""",
    )
    write(
        run_dir / "validation.log",
        """Status: pending
Command exit code: PENDING: integer.
Completed at: PENDING: ISO-8601 timestamp.
Source snapshot: PENDING: sha256:<64 hex>.
Replace with fresh output from package, closed-loop, domain, and regression checks.
Do not paste a previous run or a hand-written PASS line.
""",
    )

    prompt_hash = sha256_text(input_text.rstrip() + "\n")
    trigger_record = {
        "schema_version": "2.0",
        "run_id": run_id,
        "run_type": args.mode,
        "status": "pending",
        "input_file": "input.md",
        "input_sha256": prompt_hash,
        "attestations": {
            "host": host_attestation_ref,
            "reviewer": reviewer_attestation_ref,
        },
        "routes": [
            {
                "route": "without-skill",
                "execution_status": "pending",
                "host_runtime": None,
                "session_id": None,
                "started_at": None,
                "completed_at": None,
                "prompt_file": "prompt-without-skill.txt",
                "prompt_sha256": prompt_hash,
                "output_file": "without-skill-output.md",
                "output_sha256": None,
                "skill_loaded": False,
                "skill_source": None,
                "trigger_observed": False,
                "evidence_files": ["runtime-without-skill.log"],
            },
            {
                "route": "with-skill",
                "execution_status": "pending",
                "host_runtime": None,
                "session_id": None,
                "started_at": None,
                "completed_at": None,
                "prompt_file": "prompt-with-skill.txt",
                "prompt_sha256": prompt_hash,
                "output_file": "with-skill-output.md",
                "output_sha256": None,
                "skill_loaded": True,
                "skill_source": "meta-skill-creator/SKILL.md",
                "trigger_observed": False,
                "evidence_files": ["runtime-with-skill.log"],
            },
        ],
    }
    (run_dir / "trigger-run.json").write_text(
        json.dumps(trigger_record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Pending {args.mode} workspace created: {run_dir}")
    print("No model run, score, runtime pass, human pass, or ready decision was generated.")
    print(f"External attestations must be stored outside the run folder under: {run_dir.parent / 'attestations'}")
    print(f"After real runs and review: python {Path(__file__).with_name('check_acceptance_runs.py')} {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
