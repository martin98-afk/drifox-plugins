#!/usr/bin/env python3
"""Positive/negative regression suite for the acceptance evidence gate."""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from check_acceptance_runs import sha256_file, validate_run


def write(path: Path, content: str) -> None:
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def dump_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def replace_markdown_field(path: Path, label: str, value: str) -> None:
    prefix = f"{label}:"
    lines = path.read_text(encoding="utf-8").splitlines()
    replaced = [f"{label}: {value}" if line.startswith(prefix) else line for line in lines]
    if replaced == lines:
        raise AssertionError(f"field {label!r} not found in {path}")
    write(path, "\n".join(replaced))


def refresh_reviewer_release_hash(run_dir: Path, reviewer_path: Path) -> None:
    replace_markdown_field(
        run_dir / "release-gate.md",
        "Reviewer attestation SHA-256",
        sha256_file(reviewer_path),
    )


def iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def route_binding(route: dict[str, Any]) -> dict[str, Any]:
    return {
        field: route[field]
        for field in [
            "route",
            "host_runtime",
            "session_id",
            "started_at",
            "completed_at",
            "prompt_sha256",
            "output_sha256",
            "skill_loaded",
            "trigger_observed",
        ]
    }


def build_valid_run(root: Path, case_name: str = "positive") -> Path:
    case_root = root / case_name
    run_dir = case_root / "run"
    attestations_dir = case_root / "attestations"
    run_dir.mkdir(parents=True)
    attestations_dir.mkdir()

    base = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=2)
    times = {
        "evidence": base,
        "capability": base + timedelta(minutes=2),
        "rubric": base + timedelta(minutes=3),
        "without_start": base + timedelta(minutes=10),
        "without_end": base + timedelta(minutes=14),
        "with_start": base + timedelta(minutes=20),
        "with_end": base + timedelta(minutes=28),
        "event": base + timedelta(minutes=30),
        "host_issue": base + timedelta(minutes=31),
        "validation": base + timedelta(minutes=35),
        "review": base + timedelta(minutes=40),
        "review_issue": base + timedelta(minutes=41),
        "release": base + timedelta(minutes=45),
    }
    run_id = f"acceptance-{case_name.replace('_', '-')}-fresh"
    prompt = (
        "把重复出现的客户升级记录做成一个可复用 Skill；先研究真实工作流，"
        "再输出触发边界、交接产物、评测和发布证据。"
    )
    write(run_dir / "input.md", prompt)
    write(run_dir / "prompt-without-skill.txt", prompt)
    write(run_dir / "prompt-with-skill.txt", prompt)
    write(
        run_dir / "evidence-sweep.md",
        f"""# Evidence sweep

User material: 用户提供三份已脱敏的升级记录和一份现有交接清单。
Local / Graphify: 读取本 Skill 契约并运行 focused Graphify query 检查相邻能力。
Official / platform: 读取宿主 Skill 规范和本项目 skill standard 的当前版本。
High-signal: 对比三个公开支持交接流程，提取责任人、证据、升级和关闭条件。
Counterevidence: 行业隐私规则不同，因此示例字段不能直接成为通用默认值。
Evidence checked at: {iso(times['evidence'])}
Evidence refs: docs/skill-standard.md; skills/meta-skill-creator/SKILL.md; https://agentskills.io/specification
""",
    )

    dimensions = [
        ("user-result", 20, "Defines the user-visible result and observable success criteria.", 8, 17),
        ("domain-evidence", 20, "Separates domain evidence, counterevidence, and unsupported claims.", 8, 17),
        ("package-contract", 20, "Maps trigger boundaries, artifacts, package files, and failures.", 9, 16),
        ("runtime-honesty", 20, "Distinguishes artifact consistency from observed host execution.", 8, 16),
        ("release-honesty", 20, "Uses evidence layers and refuses readiness without required proof.", 9, 16),
    ]
    rubric = {
        "schema_version": "1.0",
        "rubric_id": "meta-skill-acceptance-v2",
        "frozen_at": iso(times["rubric"]),
        "total_weight": 100,
        "dimensions": [
            {"id": dimension_id, "weight": weight, "criterion": criterion}
            for dimension_id, weight, criterion, _, _ in dimensions
        ],
    }
    dump_json(run_dir / "scoring-rubric.json", rubric)
    rubric_hash = sha256_file(run_dir / "scoring-rubric.json")
    write(
        run_dir / "scoring-rubric.md",
        f"""# Scoring rubric

Rubric ID: meta-skill-acceptance-v2
Rubric frozen at: {iso(times['rubric'])}
Machine rubric: scoring-rubric.json
Scoring rule: each dimension is scored from zero to its declared weight; totals are recomputed.

The five dimensions were locked before either route started. Each score must cite
line evidence from both unedited outputs. The machine rubric is the authoritative
weight contract, and the external human attestation is the authoritative score record.
""",
    )
    write(
        run_dir / "without-skill-output.md",
        """# Without-skill output

The response produced a reusable reply prompt and a short handoff checklist. It named
the customer, incident, current state, next action, owner, and due date. It did not
perform domain evidence research, define a stable trigger boundary, map package files,
or specify a reproducible baseline and release gate. The result is usable as a local
template but not yet a portable Skill package.
""",
    )
    write(
        run_dir / "with-skill-output.md",
        """# With-skill output

Domain Research Brief: the repeated workflow is customer escalation handoff with
privacy, ownership, evidence, response-time, and closure constraints.
Evidence sweep: user records, local contracts, platform rules, and counterevidence
were separated before design.
Skillization Decision: make, because the task repeats, has stable inputs and outputs,
and needs consistent failure handling.
Deep Research Decision: a minimum sweep supports the local candidate; current public
platform claims would require official sources, counterevidence, and a stop rule.
Goal Contract: produce a grounded customer reply and owner-ready handoff whose facts,
next action, and completion checks are observable.
Execution Contract: extract facts, select a route, build both artifacts, validate them,
and stop or request authority when evidence or permissions are missing.
Boundary Contract: do not invent facts, send messages, promise compensation, change
accounts, or claim ready when privacy, authority, or policy evidence is incomplete.
""",
    )

    input_hash = sha256_file(run_dir / "input.md")
    prompt_without_hash = sha256_file(run_dir / "prompt-without-skill.txt")
    prompt_with_hash = sha256_file(run_dir / "prompt-with-skill.txt")
    without_hash = sha256_file(run_dir / "without-skill-output.md")
    with_hash = sha256_file(run_dir / "with-skill-output.md")
    host_ref = f"../attestations/{run_id}-host-attestation.json"
    reviewer_ref = f"../attestations/{run_id}-reviewer-attestation.json"
    trigger = {
        "schema_version": "2.0",
        "run_id": run_id,
        "run_type": "acceptance",
        "status": "completed",
        "input_file": "input.md",
        "input_sha256": input_hash,
        "attestations": {"host": host_ref, "reviewer": reviewer_ref},
        "routes": [
            {
                "route": "without-skill",
                "execution_status": "completed",
                "host_runtime": "codex-desktop",
                "session_id": f"{case_name}-session-without",
                "started_at": iso(times["without_start"]),
                "completed_at": iso(times["without_end"]),
                "prompt_file": "prompt-without-skill.txt",
                "prompt_sha256": prompt_without_hash,
                "output_file": "without-skill-output.md",
                "output_sha256": without_hash,
                "skill_loaded": False,
                "skill_source": None,
                "trigger_observed": False,
                "evidence_files": ["runtime-without-skill.log"],
            },
            {
                "route": "with-skill",
                "execution_status": "completed",
                "host_runtime": "codex-desktop",
                "session_id": f"{case_name}-session-with",
                "started_at": iso(times["with_start"]),
                "completed_at": iso(times["with_end"]),
                "prompt_file": "prompt-with-skill.txt",
                "prompt_sha256": prompt_with_hash,
                "output_file": "with-skill-output.md",
                "output_sha256": with_hash,
                "skill_loaded": True,
                "skill_source": "meta-skill-creator/SKILL.md",
                "trigger_observed": True,
                "evidence_files": ["runtime-with-skill.log"],
            },
        ],
    }
    dump_json(run_dir / "trigger-run.json", trigger)

    for route in trigger["routes"]:
        skill_lines = (
            "trigger_observed=true\nskill_source=meta-skill-creator/SKILL.md\n"
            if route["route"] == "with-skill"
            else "trigger_observed=false\nskill_source=none\n"
        )
        write(
            run_dir / route["evidence_files"][0],
            f"""host_runtime={route['host_runtime']}
session_id={route['session_id']}
route={route['route']}
started_at={route['started_at']}
completed_at={route['completed_at']}
result=completed
prompt_sha256={route['prompt_sha256']}
output_sha256={route['output_sha256']}
{skill_lines}capture=run-folder copy; occurrence is anchored by the external host event
""",
        )

    event = {
        "schema_version": "1.0",
        "event_type": "host-session-export",
        "event_id": f"host-event-{case_name}",
        "issuer": "codex-desktop-host",
        "captured_at": iso(times["event"]),
        "run_id": run_id,
        "routes": [route_binding(route) for route in trigger["routes"]],
    }
    event_path = attestations_dir / f"{run_id}-host-event.json"
    dump_json(event_path, event)
    host_attestation = {
        "schema_version": "1.0",
        "attestation_type": "host-runtime",
        "attestation_id": f"host-attestation-{case_name}",
        "issuer": "codex-desktop-host",
        "issued_at": iso(times["host_issue"]),
        "run_id": run_id,
        "input_sha256": input_hash,
        "capabilities": {
            "host_runtime": "codex-desktop",
            "python_command": "python 3.14 on Windows PowerShell",
            "skill_invocation_surface": "project Skill loader with isolated clean sessions",
        },
        "event_anchor": {"path": event_path.name, "sha256": sha256_file(event_path)},
        "routes": [route_binding(route) for route in trigger["routes"]],
    }
    host_attestation_path = attestations_dir / f"{run_id}-host-attestation.json"
    dump_json(host_attestation_path, host_attestation)

    write(
        run_dir / "tool-capability.md",
        f"""# Tool capability record

Checked at: {iso(times['capability'])}
Host runtime: codex-desktop
Python command: python 3.14 on Windows PowerShell
Skill invocation surface: project Skill loader with isolated clean sessions
Host attestation: {host_ref}
Evidence refs: runtime-without-skill.log; runtime-with-skill.log
Limitations: local copies prove consistency only; occurrence is bound by the external host event and attestation.
""",
    )

    validation_log = f"""Meta skill package check passed for the current source package.
Closed-loop check passed for the current source package.
Acceptance validator regression passed for the current source package.
Command exit code: 0
Completed at: {iso(times['validation'])}
Source snapshot: sha256:{'a' * 64}
All commands were captured from the same source snapshot and returned zero.
"""
    write(run_dir / "validation.log", validation_log)
    write(
        run_dir / "validation.md",
        f"""# Validation record

Validation command: python scripts/check_meta_skill_package.py . and python scripts/check_closed_loop.py .
Validation status: passed
Validation run at: {iso(times['validation'])}
Result evidence: validation.log
Validation log SHA-256: {sha256_file(run_dir / 'validation.log')}

The validation receipt is hash-bound to this run. It establishes artifact consistency,
not host occurrence or human acceptance; those require their external attestations.
""",
    )

    score_entries = [
        {
            "dimension_id": dimension_id,
            "without_score": without_score,
            "with_score": with_score,
            "evidence_refs": [
                "without-skill-output.md#L2-L6",
                "with-skill-output.md#L2-L16",
            ],
        }
        for dimension_id, _, _, without_score, with_score in dimensions
    ]
    totals = {
        "without": sum(entry["without_score"] for entry in score_entries),
        "with": sum(entry["with_score"] for entry in score_entries),
    }
    totals["delta"] = totals["with"] - totals["without"]
    reviewer_attestation = {
        "schema_version": "1.0",
        "attestation_type": "human-review",
        "attestation_id": f"human-review-{case_name}",
        "issuer_id": "reviewer-kim-01",
        "issued_at": iso(times["review_issue"]),
        "reviewed_at": iso(times["review"]),
        "run_id": run_id,
        "reviewer": {
            "id": "reviewer-kim-01",
            "display_name": "Kim Reviewer",
            "type": "human",
        },
        "rubric_sha256": rubric_hash,
        "outputs": {route["route"]: route["output_sha256"] for route in trigger["routes"]},
        "dimension_scores": score_entries,
        "totals": totals,
        "decision": "accepted",
    }
    reviewer_attestation_path = attestations_dir / f"{run_id}-reviewer-attestation.json"
    dump_json(reviewer_attestation_path, reviewer_attestation)
    write(
        run_dir / "reviewer-notes.md",
        f"""# Reviewer notes

Reviewer: Kim Reviewer
Reviewer ID: reviewer-kim-01
Reviewer type: human
Reviewed at: {iso(times['review'])}
Reviewer attestation: {reviewer_ref}
Rubric SHA-256: {rubric_hash}
Score summary:
Without-skill: {totals['without']}
With-skill: {totals['with']}
Delta: {totals['delta']}
Pass / partial / fail: pass
Human status: accepted

Notes:
- The external human attestation scores every frozen rubric dimension and cites line
  evidence from both unedited outputs. Totals shown here are recomputed, not typed as
  an independent release claim. Reviewer identity and review time are externally bound.
""",
    )
    write(
        run_dir / "release-gate.md",
        f"""# Release gate

Structure status: artifact_consistent
Runtime status: verified
Human status: verified
Ready decision: pass
Release decided at: {iso(times['release'])}
Host attestation SHA-256: {sha256_file(host_attestation_path)}
Reviewer attestation SHA-256: {sha256_file(reviewer_attestation_path)}
Rubric SHA-256: {rubric_hash}

Local hashes establish artifact consistency only. Runtime is verified by the external
host attestation and event anchor; human status is verified by the external reviewer
attestation. The release decision follows route execution, validation, and review.
""",
    )
    return run_dir


def external_attestation(run_dir: Path, kind: str) -> Path:
    trigger = json.loads((run_dir / "trigger-run.json").read_text(encoding="utf-8"))
    return (run_dir / trigger["attestations"][kind]).resolve()


def require_failure(run_dir: Path, expected_fragment: str) -> None:
    failures = validate_run(run_dir)
    if not failures:
        raise AssertionError(f"negative case unexpectedly passed: {run_dir.parent.name}")
    if not any(expected_fragment.casefold() in failure.casefold() for failure in failures):
        joined = "\n".join(failures)
        raise AssertionError(
            f"{run_dir.parent.name} missed expected failure {expected_fragment!r}:\n{joined}"
        )


def main() -> int:
    negative_count = 0
    with tempfile.TemporaryDirectory(prefix="meta-skill-acceptance-regression-") as tmp:
        root = Path(tmp)
        valid = build_valid_run(root, "positive")
        positive_failures = validate_run(valid)
        if positive_failures:
            raise AssertionError("positive completed run failed:\n" + "\n".join(positive_failures))

        missing_capability = build_valid_run(root, "missing-capability")
        (missing_capability / "tool-capability.md").unlink()
        require_failure(missing_capability, "missing tool-capability.md")
        negative_count += 1

        pending = build_valid_run(root, "pending-state")
        path = pending / "release-gate.md"
        path.write_text(path.read_text(encoding="utf-8").replace("Ready decision: pass", "Ready decision: pending"), encoding="utf-8")
        require_failure(pending, "placeholder/unexecuted marker")
        negative_count += 1

        missing_runtime = build_valid_run(root, "missing-runtime")
        (missing_runtime / "runtime-with-skill.log").unlink()
        require_failure(missing_runtime, "missing runtime-with-skill.log")
        negative_count += 1

        tampered = build_valid_run(root, "tampered-output")
        with (tampered / "with-skill-output.md").open("a", encoding="utf-8") as handle:
            handle.write("\nUnreviewed material added after the runtime capture.\n")
        require_failure(tampered, "output_sha256 does not match")
        negative_count += 1

        no_human = build_valid_run(root, "human-rejected")
        path = no_human / "reviewer-notes.md"
        path.write_text(path.read_text(encoding="utf-8").replace("Human status: accepted", "Human status: rejected"), encoding="utf-8")
        require_failure(no_human, "Human status must be accepted")
        negative_count += 1

        trigger_mismatch = build_valid_run(root, "trigger-mismatch")
        path = trigger_mismatch / "trigger-run.json"
        trigger = json.loads(path.read_text(encoding="utf-8"))
        trigger["routes"][1]["trigger_observed"] = False
        dump_json(path, trigger)
        require_failure(trigger_mismatch, "trigger_observed must be True")
        negative_count += 1

        trailing_space = build_valid_run(root, "same-session-space")
        path = trailing_space / "trigger-run.json"
        trigger = json.loads(path.read_text(encoding="utf-8"))
        trigger["routes"][0]["session_id"] = "same-session"
        trigger["routes"][1]["session_id"] = "same-session "
        dump_json(path, trigger)
        require_failure(trailing_space, "strip/casefold normalization")
        negative_count += 1

        case_only = build_valid_run(root, "same-session-case")
        path = case_only / "trigger-run.json"
        trigger = json.loads(path.read_text(encoding="utf-8"))
        trigger["routes"][0]["session_id"] = "SAME-SESSION"
        trigger["routes"][1]["session_id"] = "same-session"
        dump_json(path, trigger)
        require_failure(case_only, "strip/casefold normalization")
        negative_count += 1

        generic_placeholder = build_valid_run(root, "generic-placeholder")
        path = generic_placeholder / "reviewer-notes.md"
        path.write_text(path.read_text(encoding="utf-8").replace("Kim Reviewer", "{{reviewer_name}}"), encoding="utf-8")
        require_failure(generic_placeholder, "placeholder/unexecuted marker")
        negative_count += 1

        for suffix, wrapped_name in [
            ("square", "[reviewer_name]"),
            ("angle", "<reviewer_name>"),
            ("paren", "(reviewer_name)"),
            ("square-host", "[host]"),
            ("angle-session", "<session_id>"),
            ("paren-token", "(token)"),
        ]:
            wrapped_placeholder = build_valid_run(root, f"wrapped-placeholder-{suffix}")
            reviewer_path = external_attestation(wrapped_placeholder, "reviewer")
            attestation = json.loads(reviewer_path.read_text(encoding="utf-8"))
            attestation["reviewer"]["display_name"] = wrapped_name
            dump_json(reviewer_path, attestation)
            replace_markdown_field(wrapped_placeholder / "reviewer-notes.md", "Reviewer", wrapped_name)
            refresh_reviewer_release_hash(wrapped_placeholder, reviewer_path)
            require_failure(wrapped_placeholder, "placeholder/unexecuted marker")
            negative_count += 1

        unexecuted = build_valid_run(root, "unexecuted-marker")
        with (unexecuted / "tool-capability.md").open("a", encoding="utf-8") as handle:
            handle.write("\nExecution note: NOT EXECUTED; 尚未运行; 需要补充真实证据。\n")
        require_failure(unexecuted, "placeholder/unexecuted marker")
        negative_count += 1

        missing_host = build_valid_run(root, "missing-host-attestation")
        external_attestation(missing_host, "host").unlink()
        require_failure(missing_host, "external host attestation")
        negative_count += 1

        internal_host = build_valid_run(root, "internal-host-attestation")
        external = external_attestation(internal_host, "host")
        internal = internal_host / "host-attestation.json"
        shutil.copy2(external, internal)
        path = internal_host / "trigger-run.json"
        trigger = json.loads(path.read_text(encoding="utf-8"))
        trigger["attestations"]["host"] = "host-attestation.json"
        dump_json(path, trigger)
        require_failure(internal_host, "external host attestation")
        negative_count += 1

        fake_capability = build_valid_run(root, "fake-capability")
        path = fake_capability / "tool-capability.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace("Host runtime: codex-desktop", "Host runtime: fake-host")
        text = text.replace("Python command: python 3.14 on Windows PowerShell", "Python command: echo")
        path.write_text(text, encoding="utf-8")
        require_failure(fake_capability, "must match external host attestation")
        negative_count += 1

        ai_reviewer = build_valid_run(root, "ai-reviewer")
        path = external_attestation(ai_reviewer, "reviewer")
        attestation = json.loads(path.read_text(encoding="utf-8"))
        attestation["issuer_id"] = "ai-reviewer-01"
        attestation["reviewer"] = {"id": "ai-reviewer-01", "display_name": "AI Reviewer", "type": "human"}
        dump_json(path, attestation)
        notes = ai_reviewer / "reviewer-notes.md"
        text = notes.read_text(encoding="utf-8").replace("reviewer-kim-01", "ai-reviewer-01").replace("Kim Reviewer", "AI Reviewer")
        notes.write_text(text, encoding="utf-8")
        require_failure(ai_reviewer, "not AI/automation")
        negative_count += 1

        for suffix, non_human_name in [
            ("artificial-intelligence", "Artificial Intelligence Reviewer"),
            ("a-dot-i", "A.I. Reviewer"),
            ("machine-service", "Machine Review Service"),
            ("automated", "Automated Reviewer"),
            ("model", "Model Reviewer"),
            ("bot", "Review Bot"),
            ("service", "Reviewer Service"),
        ]:
            disguised_ai = build_valid_run(root, f"ai-reviewer-{suffix}")
            reviewer_path = external_attestation(disguised_ai, "reviewer")
            attestation = json.loads(reviewer_path.read_text(encoding="utf-8"))
            attestation["reviewer"]["display_name"] = non_human_name
            dump_json(reviewer_path, attestation)
            replace_markdown_field(disguised_ai / "reviewer-notes.md", "Reviewer", non_human_name)
            refresh_reviewer_release_hash(disguised_ai, reviewer_path)
            require_failure(disguised_ai, "not AI/automation")
            negative_count += 1

        alternate_fixed_totals = build_valid_run(root, "alternate-fixed-totals")
        path = alternate_fixed_totals / "reviewer-notes.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace("Without-skill: 42", "Without-skill: 36")
        text = text.replace("With-skill: 82", "With-skill: 89")
        text = text.replace("Delta: 40", "Delta: 53")
        path.write_text(text, encoding="utf-8")
        require_failure(alternate_fixed_totals, "totals must match recomputed dimension scores")
        negative_count += 1

        forged_dimension_totals = build_valid_run(root, "forged-dimension-totals")
        path = external_attestation(forged_dimension_totals, "reviewer")
        attestation = json.loads(path.read_text(encoding="utf-8"))
        attestation["totals"] = {"without": 36, "with": 89, "delta": 53}
        dump_json(path, attestation)
        require_failure(forged_dimension_totals, "recomputed from per-dimension scores")
        negative_count += 1

        impossible_line_refs = build_valid_run(root, "fixed-score-impossible-lines")
        reviewer_path = external_attestation(impossible_line_refs, "reviewer")
        attestation = json.loads(reviewer_path.read_text(encoding="utf-8"))
        for score in attestation["dimension_scores"]:
            score["evidence_refs"] = [
                "without-skill-output.md#L999999",
                "with-skill-output.md#L999999",
            ]
        dump_json(reviewer_path, attestation)
        refresh_reviewer_release_hash(impossible_line_refs, reviewer_path)
        require_failure(impossible_line_refs, "line range is invalid")
        negative_count += 1

        blank_line_refs = build_valid_run(root, "fixed-score-blank-lines")
        reviewer_path = external_attestation(blank_line_refs, "reviewer")
        attestation = json.loads(reviewer_path.read_text(encoding="utf-8"))
        for score in attestation["dimension_scores"]:
            score["evidence_refs"] = [
                "without-skill-output.md#L2",
                "with-skill-output.md#L2",
            ]
        dump_json(reviewer_path, attestation)
        refresh_reviewer_release_hash(blank_line_refs, reviewer_path)
        require_failure(blank_line_refs, "empty or non-substantive content")
        negative_count += 1

        wrong_output_refs = build_valid_run(root, "fixed-score-wrong-output")
        reviewer_path = external_attestation(wrong_output_refs, "reviewer")
        attestation = json.loads(reviewer_path.read_text(encoding="utf-8"))
        for score in attestation["dimension_scores"]:
            score["evidence_refs"] = [
                "without-skill-output.md#L3-L6",
                "without-skill-output.md#L7",
            ]
        dump_json(reviewer_path, attestation)
        refresh_reviewer_release_hash(wrong_output_refs, reviewer_path)
        require_failure(wrong_output_refs, "with-skill-output.md")
        negative_count += 1

        missing_reviewer = build_valid_run(root, "missing-reviewer-attestation")
        external_attestation(missing_reviewer, "reviewer").unlink()
        require_failure(missing_reviewer, "external reviewer attestation")
        negative_count += 1

        coordinated_internal_rewrite = build_valid_run(root, "coordinated-internal-rewrite")
        output = coordinated_internal_rewrite / "with-skill-output.md"
        old_hash = sha256_file(output)
        write(
            output,
            "# With-skill output\n\nDomain Research Brief. Evidence sweep. Skillization Decision. "
            "Deep Research Decision. Goal Contract. Execution Contract. Boundary Contract. "
            "This replacement contains only gate keywords and padding, carries no usable "
            "analysis, and was written after the external host event was captured.",
        )
        new_hash = sha256_file(output)
        path = coordinated_internal_rewrite / "trigger-run.json"
        trigger = json.loads(path.read_text(encoding="utf-8"))
        trigger["routes"][1]["output_sha256"] = new_hash
        dump_json(path, trigger)
        runtime = coordinated_internal_rewrite / "runtime-with-skill.log"
        runtime.write_text(runtime.read_text(encoding="utf-8").replace(old_hash, new_hash), encoding="utf-8")
        require_failure(coordinated_internal_rewrite, "host attestation with-skill field 'output_sha256'")
        negative_count += 1

        future_timestamp = build_valid_run(root, "future-timestamp")
        path = future_timestamp / "tool-capability.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace(text.split("Checked at: ", 1)[1].splitlines()[0], "2099-01-01T00:00:00+00:00")
        path.write_text(text, encoding="utf-8")
        require_failure(future_timestamp, "must not be in the future")
        negative_count += 1

        review_before_run = build_valid_run(root, "review-before-run")
        trigger = json.loads((review_before_run / "trigger-run.json").read_text(encoding="utf-8"))
        early_review = trigger["routes"][0]["started_at"]
        path = external_attestation(review_before_run, "reviewer")
        attestation = json.loads(path.read_text(encoding="utf-8"))
        attestation["reviewed_at"] = early_review
        dump_json(path, attestation)
        notes = review_before_run / "reviewer-notes.md"
        text = notes.read_text(encoding="utf-8")
        current = text.split("Reviewed at: ", 1)[1].splitlines()[0]
        notes.write_text(text.replace(current, early_review), encoding="utf-8")
        require_failure(review_before_run, "human review must follow")
        negative_count += 1

        release_before_review = build_valid_run(root, "release-before-review")
        trigger = json.loads((release_before_review / "trigger-run.json").read_text(encoding="utf-8"))
        early_release = trigger["routes"][1]["completed_at"]
        path = release_before_review / "release-gate.md"
        text = path.read_text(encoding="utf-8")
        current = text.split("Release decided at: ", 1)[1].splitlines()[0]
        path.write_text(text.replace(current, early_release), encoding="utf-8")
        require_failure(release_before_review, "release decision must follow")
        negative_count += 1

    print(f"Acceptance validator regression passed: 1 positive and {negative_count} negative cases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
