#!/usr/bin/env python3
"""Fail-closed validator for completed meta-skill-creator acceptance runs.

Run-folder files can prove only artifact consistency. Runtime and human status are
verified only when independently stored host/reviewer attestations bind the run,
rubric, sessions, prompts, outputs, timestamps, and an external host event anchor.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REQUIRED_TEXT_FILES = {
    "input.md": 12,
    "prompt-without-skill.txt": 12,
    "prompt-with-skill.txt": 12,
    "evidence-sweep.md": 160,
    "tool-capability.md": 180,
    "without-skill-output.md": 160,
    "with-skill-output.md": 160,
    "runtime-without-skill.log": 80,
    "runtime-with-skill.log": 80,
    "scoring-rubric.md": 180,
    "reviewer-notes.md": 260,
    "release-gate.md": 220,
    "validation.md": 160,
    "validation.log": 120,
}

REQUIRED_JSON_FILES = ["trigger-run.json", "scoring-rubric.json"]

REQUIRED_PHRASES = {
    "evidence-sweep.md": [
        "User material:",
        "Local / Graphify:",
        "Official / platform:",
        "High-signal:",
        "Counterevidence:",
        "Evidence checked at:",
        "Evidence refs:",
    ],
    "tool-capability.md": [
        "Checked at:",
        "Host runtime:",
        "Python command:",
        "Skill invocation surface:",
        "Host attestation:",
        "Evidence refs:",
        "Limitations:",
    ],
    "scoring-rubric.md": [
        "Rubric ID:",
        "Rubric frozen at:",
        "Machine rubric:",
        "Scoring rule:",
    ],
    "with-skill-output.md": [
        "Domain Research Brief",
        "Evidence sweep",
        "Skillization Decision",
        "Deep Research Decision",
        "Goal Contract",
        "Execution Contract",
        "Boundary Contract",
    ],
    "reviewer-notes.md": [
        "Reviewer:",
        "Reviewer ID:",
        "Reviewer type:",
        "Reviewed at:",
        "Reviewer attestation:",
        "Rubric SHA-256:",
        "Score summary:",
        "Without-skill:",
        "With-skill:",
        "Delta:",
        "Pass / partial / fail:",
        "Human status:",
    ],
    "release-gate.md": [
        "Structure status:",
        "Runtime status:",
        "Human status:",
        "Ready decision:",
        "Release decided at:",
        "Host attestation SHA-256:",
        "Reviewer attestation SHA-256:",
        "Rubric SHA-256:",
    ],
    "validation.md": [
        "Validation command:",
        "Validation status:",
        "Validation run at:",
        "Result evidence:",
        "Validation log SHA-256:",
    ],
    "validation.log": [
        "Meta skill package check passed",
        "Closed-loop check passed",
        "Acceptance validator regression passed",
        "Command exit code:",
        "Completed at:",
        "Source snapshot:",
    ],
}

# These patterns reject placeholder syntax and semantic "not run yet" markers.
# Wrapped identifiers are limited to placeholder-shaped names so normal Markdown
# links and ordinary prose brackets do not become false positives.
WRAPPED_PLACEHOLDER_IDENTIFIER = (
    r"(?:"
    r"(?:reviewer|host|session|token|issuer|user|account|api|secret)"
    r"(?:[ _-]*(?:name|id|runtime|value|key|path|ref|reference))?"
    r"|(?:name|id|value|field|path|file|time|date|timestamp|hash|sha256)"
    r"|(?:your|insert|replace|pending|todo|tbd)[ _-]*[A-Za-z0-9_-]*"
    r"|[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+"
    r")"
)
PLACEHOLDER_PATTERNS = [
    re.compile(pattern, re.I)
    for pattern in [
        r"\{\{[^{}\r\n]{1,160}\}\}",
        r"\{%[^%\r\n]{1,160}%\}",
        r"\$\{[^{}\r\n]{1,160}\}",
        r"\[\[[^\[\]\r\n]{1,160}\]\]",
        rf"(?<!\!)\[\s*{WRAPPED_PLACEHOLDER_IDENTIFIER}\s*\](?!\s*\()",
        rf"<\s*{WRAPPED_PLACEHOLDER_IDENTIFIER}\s*>",
        rf"\(\s*{WRAPPED_PLACEHOLDER_IDENTIFIER}\s*\)",
        r"<\s*[^>]*(?:fill|replace|pending|todo|tbd|tba|placeholder|insert|your)[^>]*>",
        r"\b(?:todo|tbd|tba|pending|placeholder|fill[-_ ]?(?:here|after|me)|replace[-_ ]?(?:here|me)|not[-_ ]?(?:executed|run|reviewed|captured)|unexecuted|unreviewed)\b",
        r"待填|待补|待执行|替换这里|占位|尚未(?:执行|运行|审核|评审|填写|完成|验证)|未(?:执行|运行|审核|评审|填写|完成|验证)|需要补充|稍后补充|示例值|样例值",
    ]
]

NON_HUMAN_REVIEWER_PATTERNS = [
    re.compile(pattern, re.I)
    for pattern in [
        r"(?:^|[^a-z0-9])(?:ai|llm|gpt|claude|assistant|agent|model|bot|automated)(?:$|[^a-z0-9])",
        r"(?:^|[^a-z0-9])a(?:[\W_]*?)i(?:$|[^a-z0-9])",
        r"artificial[\s._-]*intelligence",
        r"machine[\s._-]*(?:review|reviewer|reviewing|evaluation|judge|scorer|scoring|service)",
        r"(?:^|[^a-z0-9])(?:automation|service)(?:$|[^a-z0-9])",
        r"(?:^|[^a-z0-9])(?:anonymous|anon|unknown|n/?a|none)(?:$|[^a-z0-9])",
        r"人工智能|语言模型|机器人|自动审核|匿名|未知审核人|无人审核",
    ]
]

CONTROL_FILES = {
    "input.md",
    "prompt-without-skill.txt",
    "prompt-with-skill.txt",
    "trigger-run.json",
    "scoring-rubric.json",
    "reviewer-notes.md",
    "release-gate.md",
    "validation.md",
    "with-skill-output.md",
    "without-skill-output.md",
}

ROUTE_EXPECTATIONS = {
    "without-skill": {
        "prompt_file": "prompt-without-skill.txt",
        "output_file": "without-skill-output.md",
        "skill_loaded": False,
        "trigger_observed": False,
        "evidence_file": "runtime-without-skill.log",
    },
    "with-skill": {
        "prompt_file": "prompt-with-skill.txt",
        "output_file": "with-skill-output.md",
        "skill_loaded": True,
        "trigger_observed": True,
        "evidence_file": "runtime-with-skill.log",
    },
}

SCORE_EVIDENCE_REF = re.compile(
    r"^(?P<file>without-skill-output\.md|with-skill-output\.md)"
    r"#L(?P<start>[1-9]\d*)(?:-L?(?P<end>[1-9]\d*))?$",
    re.I,
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def placeholder_hits(text: str) -> list[str]:
    hits: list[str] = []
    for pattern in PLACEHOLDER_PATTERNS:
        match = pattern.search(text)
        if match:
            hits.append(match.group(0))
    return hits


def parse_iso8601(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def require_timestamp(label: str, value: Any, failures: list[str], now: datetime) -> datetime | None:
    parsed = parse_iso8601(value)
    if parsed is None:
        failures.append(f"{label} must be an ISO-8601 timestamp with timezone")
        return None
    if parsed > now:
        failures.append(f"{label} must not be in the future")
    return parsed


def extract_field(text: str, label: str) -> str | None:
    match = re.search(rf"^\s*{re.escape(label)}\s*:\s*(.+?)\s*$", text, re.I | re.M)
    return match.group(1).strip() if match else None


def parse_score(text: str) -> tuple[int | None, int | None, int | None]:
    values: dict[str, int | None] = {"without": None, "with": None, "delta": None}
    for label, key in [("Without-skill", "without"), ("With-skill", "with"), ("Delta", "delta")]:
        match = re.search(rf"^\s*{re.escape(label)}\s*:\s*(-?\d+)\s*$", text, re.I | re.M)
        if match:
            values[key] = int(match.group(1))
    return values["without"], values["with"], values["delta"]


def normalize_identifier(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def is_safe_identifier(value: Any, minimum: int = 6) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(rf"[A-Za-z0-9._:@/-]{{{minimum},160}}", value.strip()))


def is_human_reviewer(value: Any) -> bool:
    if not isinstance(value, str) or len(value.strip()) < 4 or placeholder_hits(value):
        return False
    return not any(pattern.search(value.casefold()) for pattern in NON_HUMAN_REVIEWER_PATTERNS)


def load_json(path: Path, label: str, failures: list[str]) -> dict[str, Any] | None:
    try:
        data = json.loads(read(path))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        failures.append(f"{label} is invalid JSON: {exc}")
        return None
    if not isinstance(data, dict):
        failures.append(f"{label} must contain a JSON object")
        return None
    return data


def resolve_internal_path(run_dir: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = (run_dir / value).resolve()
    try:
        candidate.relative_to(run_dir.resolve())
    except ValueError:
        return None
    return candidate


def resolve_external_path(run_dir: Path, value: Any, base: Path | None = None) -> Path | None:
    """Resolve a sibling attestation/anchor, never a file inside the run folder.

    External evidence is intentionally limited to the run folder's parent tree so
    a record cannot make the validator read arbitrary machine paths.
    """

    if not isinstance(value, str) or not value.strip():
        return None
    raw = Path(value.strip())
    candidate = raw.resolve() if raw.is_absolute() else ((base or run_dir) / raw).resolve()
    allowed_root = run_dir.parent.resolve()
    try:
        candidate.relative_to(allowed_root)
    except ValueError:
        return None
    try:
        candidate.relative_to(run_dir.resolve())
    except ValueError:
        return candidate
    return None


def validate_score_evidence_refs(
    run_dir: Path,
    dimension_id: str,
    refs: Any,
    failures: list[str],
) -> None:
    """Validate line-bound evidence for one rubric dimension and both outputs."""

    label = f"{run_dir}: reviewer dimension {dimension_id!r}"
    if not isinstance(refs, list) or not refs or not all(isinstance(item, str) for item in refs):
        failures.append(f"{label} needs a list of concrete evidence_refs")
        return

    covered_outputs: set[str] = set()
    seen_refs: set[str] = set()
    for ref in refs:
        if ref != ref.strip() or ref.casefold() in seen_refs:
            failures.append(f"{label} evidence_ref is blank-padded or duplicated: {ref!r}")
            continue
        seen_refs.add(ref.casefold())
        match = SCORE_EVIDENCE_REF.fullmatch(ref)
        if match is None:
            failures.append(
                f"{label} evidence_ref must be an output-relative line or range such as "
                f"without-skill-output.md#L2-L6: {ref!r}"
            )
            continue

        file_name = match.group("file").casefold()
        evidence_path = resolve_internal_path(run_dir, match.group("file"))
        expected_path = (run_dir / file_name).resolve()
        if evidence_path is None or evidence_path != expected_path or not evidence_path.is_file():
            failures.append(f"{label} evidence_ref file does not exist inside the run: {ref!r}")
            continue

        start = int(match.group("start"))
        end = int(match.group("end") or start)
        lines = read(evidence_path).splitlines()
        if end < start or end - start > 200 or start > len(lines) or end > len(lines):
            failures.append(
                f"{label} evidence_ref line range is invalid for {file_name} "
                f"({len(lines)} lines): {ref!r}"
            )
            continue
        excerpt = "\n".join(lines[start - 1 : end]).strip()
        if len(excerpt) < 8 or not re.search(r"[A-Za-z0-9\u3400-\u9fff]", excerpt):
            failures.append(f"{label} evidence_ref resolves to empty or non-substantive content: {ref!r}")
            continue
        hits = placeholder_hits(excerpt)
        if hits:
            failures.append(f"{label} evidence_ref resolves to placeholder content {hits[0]!r}: {ref!r}")
            continue
        covered_outputs.add(file_name)

    for expected in ["without-skill-output.md", "with-skill-output.md"]:
        if expected not in covered_outputs:
            failures.append(
                f"{label} needs valid, existing line evidence from {expected} bound to this dimension"
            )


def route_map(data: Any) -> dict[str, dict[str, Any]] | None:
    if not isinstance(data, list):
        return None
    mapped = {item.get("route"): item for item in data if isinstance(item, dict)}
    if len(data) != 2 or set(mapped) != set(ROUTE_EXPECTATIONS):
        return None
    return mapped


def validate_route_binding(
    label: str,
    bound_route: dict[str, Any],
    trigger_route: dict[str, Any],
    failures: list[str],
) -> None:
    for field in [
        "route",
        "started_at",
        "completed_at",
        "prompt_sha256",
        "output_sha256",
        "skill_loaded",
        "trigger_observed",
    ]:
        if bound_route.get(field) != trigger_route.get(field):
            failures.append(f"{label} field {field!r} does not match trigger-run.json")
    for field in ["host_runtime", "session_id"]:
        left = bound_route.get(field)
        right = trigger_route.get(field)
        if not isinstance(left, str) or not isinstance(right, str) or normalize_identifier(left) != normalize_identifier(right):
            failures.append(f"{label} field {field!r} does not match trigger-run.json")


def validate_host_attestation(
    run_dir: Path,
    trigger: dict[str, Any],
    trigger_routes: dict[str, dict[str, Any]],
    run_completed_at: datetime | None,
    failures: list[str],
    now: datetime,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "valid": False,
        "path": None,
        "sha256": None,
        "issued_at": None,
        "capabilities": None,
    }
    attestations = trigger.get("attestations")
    host_ref = attestations.get("host") if isinstance(attestations, dict) else None
    host_path = resolve_external_path(run_dir, host_ref)
    if host_path is None or host_path.suffix.casefold() != ".json" or not host_path.is_file():
        failures.append(
            f"{run_dir}: external host attestation is missing or not a sibling JSON file; "
            "runtime evidence remains artifact_consistent only"
        )
        return result

    result["path"] = host_path
    result["sha256"] = sha256_file(host_path)
    before = len(failures)
    attestation = load_json(host_path, f"{run_dir}: host attestation", failures)
    if attestation is None:
        return result
    if attestation.get("schema_version") != "1.0" or attestation.get("attestation_type") != "host-runtime":
        failures.append(f"{run_dir}: host attestation schema/type is invalid")
    if not is_safe_identifier(attestation.get("attestation_id"), 8):
        failures.append(f"{run_dir}: host attestation needs a stable attestation_id")
    issuer = attestation.get("issuer")
    if not is_safe_identifier(issuer, 3) or placeholder_hits(str(issuer)):
        failures.append(f"{run_dir}: host attestation needs a concrete issuer")
    issued_at = require_timestamp(
        f"{run_dir}: host attestation issued_at", attestation.get("issued_at"), failures, now
    )
    result["issued_at"] = issued_at
    if attestation.get("run_id") != trigger.get("run_id"):
        failures.append(f"{run_dir}: host attestation run_id does not match trigger-run.json")
    if attestation.get("input_sha256") != trigger.get("input_sha256"):
        failures.append(f"{run_dir}: host attestation input_sha256 does not match trigger-run.json")

    capabilities = attestation.get("capabilities")
    if not isinstance(capabilities, dict):
        failures.append(f"{run_dir}: host attestation needs structured capabilities")
    else:
        for field in ["host_runtime", "python_command", "skill_invocation_surface"]:
            value = capabilities.get(field)
            if not isinstance(value, str) or len(value.strip()) < 3 or placeholder_hits(value):
                failures.append(f"{run_dir}: host attestation capability {field!r} is not concrete")
        route_runtimes = {
            normalize_identifier(route.get("host_runtime", "")) for route in trigger_routes.values()
        }
        if len(route_runtimes) != 1 or normalize_identifier(str(capabilities.get("host_runtime", ""))) not in route_runtimes:
            failures.append(f"{run_dir}: host attestation capability host_runtime must match both routes")
        result["capabilities"] = capabilities

    attested_routes = route_map(attestation.get("routes"))
    if attested_routes is None:
        failures.append(f"{run_dir}: host attestation needs exactly the two bound routes")
    else:
        for name in ROUTE_EXPECTATIONS:
            validate_route_binding(
                f"{run_dir}: host attestation {name}", attested_routes[name], trigger_routes[name], failures
            )

    anchor = attestation.get("event_anchor")
    if not isinstance(anchor, dict):
        failures.append(f"{run_dir}: host attestation needs an external event_anchor")
        anchor_path = None
    else:
        anchor_path = resolve_external_path(run_dir, anchor.get("path"), host_path.parent)
        expected_anchor_hash = anchor.get("sha256")
        if anchor_path is None or anchor_path.suffix.casefold() != ".json" or not anchor_path.is_file():
            failures.append(f"{run_dir}: host event anchor must be an external sibling JSON file")
        elif expected_anchor_hash != sha256_file(anchor_path):
            failures.append(f"{run_dir}: host event anchor SHA-256 does not match the anchored file")

    captured_at: datetime | None = None
    if anchor_path is not None and anchor_path.is_file():
        event = load_json(anchor_path, f"{run_dir}: host event anchor", failures)
        if event is not None:
            if event.get("schema_version") != "1.0" or event.get("event_type") != "host-session-export":
                failures.append(f"{run_dir}: host event anchor schema/type is invalid")
            if not is_safe_identifier(event.get("event_id"), 8):
                failures.append(f"{run_dir}: host event anchor needs a stable event_id")
            if event.get("issuer") != issuer:
                failures.append(f"{run_dir}: host event anchor issuer does not match host attestation")
            if event.get("run_id") != trigger.get("run_id"):
                failures.append(f"{run_dir}: host event anchor run_id does not match trigger-run.json")
            captured_at = require_timestamp(
                f"{run_dir}: host event anchor captured_at", event.get("captured_at"), failures, now
            )
            event_routes = route_map(event.get("routes"))
            if event_routes is None:
                failures.append(f"{run_dir}: host event anchor needs exactly the two bound routes")
            else:
                for name in ROUTE_EXPECTATIONS:
                    validate_route_binding(
                        f"{run_dir}: host event anchor {name}", event_routes[name], trigger_routes[name], failures
                    )

    if run_completed_at and captured_at and captured_at < run_completed_at:
        failures.append(f"{run_dir}: host event anchor must be captured after both routes complete")
    if captured_at and issued_at and issued_at < captured_at:
        failures.append(f"{run_dir}: host attestation issued_at must follow event capture")
    if run_completed_at and issued_at and issued_at < run_completed_at:
        failures.append(f"{run_dir}: host attestation issued_at must follow both route completions")

    result["valid"] = len(failures) == before
    return result


def validate_trigger_run(run_dir: Path, failures: list[str], now: datetime) -> dict[str, Any]:
    context: dict[str, Any] = {
        "trigger": None,
        "routes": None,
        "earliest_started_at": None,
        "run_completed_at": None,
        "host": {
            "valid": False,
            "path": None,
            "sha256": None,
            "issued_at": None,
            "capabilities": None,
        },
        "reviewer_ref": None,
    }
    path = run_dir / "trigger-run.json"
    if not path.exists():
        failures.append(f"{run_dir}: missing trigger-run.json")
        return context
    data = load_json(path, f"{run_dir}: trigger-run.json", failures)
    if data is None:
        return context
    context["trigger"] = data

    if data.get("schema_version") != "2.0":
        failures.append(f"{run_dir}: trigger-run.json schema_version must be 2.0")
    run_id = data.get("run_id")
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]{8,120}", run_id):
        failures.append(f"{run_dir}: trigger-run.json run_id is missing or unsafe")
    if data.get("run_type") not in {"acceptance", "baseline", "regression"}:
        failures.append(f"{run_dir}: trigger-run.json run_type is invalid")
    if data.get("status") != "completed":
        failures.append(f"{run_dir}: trigger-run.json status must be completed after real execution")
    if data.get("input_file") != "input.md":
        failures.append(f"{run_dir}: trigger-run.json input_file must be input.md")

    input_path = run_dir / "input.md"
    if input_path.exists() and data.get("input_sha256") != sha256_file(input_path):
        failures.append(f"{run_dir}: trigger-run.json input_sha256 does not match input.md")

    attestations = data.get("attestations")
    if not isinstance(attestations, dict):
        failures.append(f"{run_dir}: trigger-run.json needs external host and reviewer attestations")
    else:
        context["reviewer_ref"] = attestations.get("reviewer")

    routes = route_map(data.get("routes"))
    if routes is None:
        failures.append(f"{run_dir}: trigger-run.json needs exactly without-skill and with-skill routes")
        return context
    context["routes"] = routes

    sessions: set[str] = set()
    started_times: list[datetime] = []
    completed_times: list[datetime] = []
    for route_name, expected in ROUTE_EXPECTATIONS.items():
        route = routes[route_name]
        prefix = f"{run_dir}: trigger-run.json {route_name}"
        if route.get("route") != route_name:
            failures.append(f"{prefix} route name is inconsistent")
        if route.get("execution_status") != "completed":
            failures.append(f"{prefix} execution_status must be completed")
        if route.get("skill_loaded") is not expected["skill_loaded"]:
            failures.append(f"{prefix} skill_loaded must be {expected['skill_loaded']}")
        if route.get("trigger_observed") is not expected["trigger_observed"]:
            failures.append(f"{prefix} trigger_observed must be {expected['trigger_observed']}")
        if route.get("prompt_file") != expected["prompt_file"]:
            failures.append(f"{prefix} prompt_file must be {expected['prompt_file']}")
        if route.get("output_file") != expected["output_file"]:
            failures.append(f"{prefix} output_file must be {expected['output_file']}")

        host_runtime = route.get("host_runtime")
        if not isinstance(host_runtime, str) or len(host_runtime.strip()) < 2 or placeholder_hits(host_runtime):
            failures.append(f"{prefix} host_runtime needs a concrete runtime name")
        session_id = route.get("session_id")
        if not isinstance(session_id, str) or len(session_id.strip()) < 6 or placeholder_hits(session_id):
            failures.append(f"{prefix} session_id needs host evidence")
        else:
            session_key = normalize_identifier(session_id)
            if session_key in sessions:
                failures.append(
                    f"{run_dir}: clean-session routes must remain distinct after session_id strip/casefold normalization"
                )
            sessions.add(session_key)

        started = require_timestamp(f"{prefix} started_at", route.get("started_at"), failures, now)
        completed = require_timestamp(f"{prefix} completed_at", route.get("completed_at"), failures, now)
        if started:
            started_times.append(started)
        if completed:
            completed_times.append(completed)
        if started and completed and completed < started:
            failures.append(f"{prefix} completed_at is earlier than started_at")

        prompt_path = run_dir / expected["prompt_file"]
        output_path = run_dir / expected["output_file"]
        if prompt_path.exists() and route.get("prompt_sha256") != sha256_file(prompt_path):
            failures.append(f"{prefix} prompt_sha256 does not match {expected['prompt_file']}")
        if output_path.exists() and route.get("output_sha256") != sha256_file(output_path):
            failures.append(f"{prefix} output_sha256 does not match {expected['output_file']}")

        if expected["skill_loaded"]:
            skill_source = route.get("skill_source")
            if not isinstance(skill_source, str) or "meta-skill-creator" not in skill_source:
                failures.append(f"{prefix} skill_source must identify the loaded meta-skill-creator")
        elif route.get("skill_source") not in {None, "none"}:
            failures.append(f"{prefix} skill_source must be null or none")

        evidence_files = route.get("evidence_files")
        if not isinstance(evidence_files, list) or expected["evidence_file"] not in evidence_files:
            failures.append(f"{prefix} evidence_files must include {expected['evidence_file']}")
            continue
        for evidence_value in evidence_files:
            evidence_path = resolve_internal_path(run_dir, evidence_value)
            if evidence_path is None:
                failures.append(f"{prefix} has unsafe internal evidence path: {evidence_value!r}")
                continue
            rel = evidence_path.relative_to(run_dir.resolve()).as_posix()
            if rel in CONTROL_FILES:
                failures.append(f"{prefix} cannot use control/output file as runtime artifact: {rel}")
                continue
            if not evidence_path.is_file():
                failures.append(f"{prefix} evidence file does not exist: {rel}")
                continue
            evidence_text = read(evidence_path)
            if len(evidence_text.strip()) < 80 or placeholder_hits(evidence_text):
                failures.append(f"{prefix} evidence file is thin or pending: {rel}")
                continue
            for token in [str(session_id), route_name, str(route.get("prompt_sha256")), str(route.get("output_sha256"))]:
                if token not in evidence_text:
                    failures.append(f"{prefix} evidence file {rel} is not bound to {token!r}")

    if started_times:
        context["earliest_started_at"] = min(started_times)
    if completed_times:
        context["run_completed_at"] = max(completed_times)
    context["host"] = validate_host_attestation(
        run_dir, data, routes, context["run_completed_at"], failures, now
    )
    return context


def validate_rubric(
    run_dir: Path,
    failures: list[str],
    now: datetime,
    earliest_started_at: datetime | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "valid": False,
        "hash": None,
        "id": None,
        "frozen_at": None,
        "dimensions": {},
    }
    path = run_dir / "scoring-rubric.json"
    if not path.exists():
        failures.append(f"{run_dir}: missing scoring-rubric.json")
        return result
    before = len(failures)
    data = load_json(path, f"{run_dir}: scoring-rubric.json", failures)
    if data is None:
        return result
    result["hash"] = sha256_file(path)
    if data.get("schema_version") != "1.0":
        failures.append(f"{run_dir}: scoring-rubric.json schema_version must be 1.0")
    rubric_id = data.get("rubric_id")
    if not is_safe_identifier(rubric_id, 6):
        failures.append(f"{run_dir}: scoring-rubric.json needs a stable rubric_id")
    result["id"] = rubric_id
    frozen_at = require_timestamp(
        f"{run_dir}: scoring-rubric.json frozen_at", data.get("frozen_at"), failures, now
    )
    result["frozen_at"] = frozen_at
    if frozen_at and earliest_started_at and frozen_at > earliest_started_at:
        failures.append(f"{run_dir}: rubric must be frozen before either route starts")

    dimensions = data.get("dimensions")
    dimension_map: dict[str, dict[str, Any]] = {}
    if not isinstance(dimensions, list) or not 3 <= len(dimensions) <= 30:
        failures.append(f"{run_dir}: rubric needs 3-30 weighted dimensions")
    else:
        total_weight = 0
        for index, dimension in enumerate(dimensions):
            if not isinstance(dimension, dict):
                failures.append(f"{run_dir}: rubric dimension {index} must be an object")
                continue
            dimension_id = dimension.get("id")
            weight = dimension.get("weight")
            criterion = dimension.get("criterion")
            if not is_safe_identifier(dimension_id, 3):
                failures.append(f"{run_dir}: rubric dimension {index} needs a stable id")
                continue
            normalized_id = normalize_identifier(dimension_id)
            if normalized_id in dimension_map:
                failures.append(f"{run_dir}: rubric dimension ids must be unique")
                continue
            if isinstance(weight, bool) or not isinstance(weight, int) or not 1 <= weight <= 100:
                failures.append(f"{run_dir}: rubric dimension {dimension_id!r} has invalid weight")
                continue
            if not isinstance(criterion, str) or len(criterion.strip()) < 12 or placeholder_hits(criterion):
                failures.append(f"{run_dir}: rubric dimension {dimension_id!r} needs an observable criterion")
                continue
            dimension_map[normalized_id] = dimension
            total_weight += weight
        if total_weight != 100 or data.get("total_weight") != 100:
            failures.append(f"{run_dir}: rubric dimension weights and total_weight must both sum to 100")
    result["dimensions"] = dimension_map

    human = run_dir / "scoring-rubric.md"
    if human.exists():
        text = read(human)
        if extract_field(text, "Rubric ID") != rubric_id:
            failures.append(f"{run_dir}: scoring-rubric.md Rubric ID must match scoring-rubric.json")
        human_frozen = require_timestamp(
            f"{run_dir}: scoring-rubric.md Rubric frozen at",
            extract_field(text, "Rubric frozen at"),
            failures,
            now,
        )
        if human_frozen and frozen_at and human_frozen != frozen_at:
            failures.append(f"{run_dir}: scoring-rubric.md frozen time must match scoring-rubric.json")
        if extract_field(text, "Machine rubric") != "scoring-rubric.json":
            failures.append(f"{run_dir}: scoring-rubric.md Machine rubric must be scoring-rubric.json")

    result["valid"] = len(failures) == before
    return result


def validate_reviewer_attestation(
    run_dir: Path,
    notes: str,
    context: dict[str, Any],
    rubric: dict[str, Any],
    validation_at: datetime | None,
    failures: list[str],
    now: datetime,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "valid": False,
        "path": None,
        "sha256": None,
        "reviewed_at": None,
        "issued_at": None,
    }
    reviewer_ref = context.get("reviewer_ref")
    reviewer_path = resolve_external_path(run_dir, reviewer_ref)
    if reviewer_path is None or reviewer_path.suffix.casefold() != ".json" or not reviewer_path.is_file():
        failures.append(
            f"{run_dir}: external reviewer attestation is missing or not a sibling JSON file; "
            "human evidence remains unverified"
        )
        return result
    result["path"] = reviewer_path
    result["sha256"] = sha256_file(reviewer_path)
    before = len(failures)

    notes_reviewer = extract_field(notes, "Reviewer")
    notes_reviewer_id = extract_field(notes, "Reviewer ID")
    notes_reviewer_type = (extract_field(notes, "Reviewer type") or "").casefold()
    notes_reviewed_at = require_timestamp(
        f"{run_dir}: reviewer-notes.md Reviewed at", extract_field(notes, "Reviewed at"), failures, now
    )
    notes_rubric_hash = extract_field(notes, "Rubric SHA-256")
    notes_attestation_ref = extract_field(notes, "Reviewer attestation")
    if resolve_external_path(run_dir, notes_attestation_ref) != reviewer_path:
        failures.append(f"{run_dir}: reviewer-notes.md must reference the external reviewer attestation")
    if notes_reviewer_type != "human":
        failures.append(f"{run_dir}: Reviewer type must be human")
    if not is_human_reviewer(notes_reviewer) or not is_human_reviewer(notes_reviewer_id):
        failures.append(f"{run_dir}: reviewer identity must identify a non-anonymous human, not AI/automation")
    if notes_rubric_hash != rubric.get("hash"):
        failures.append(f"{run_dir}: reviewer-notes.md Rubric SHA-256 does not match scoring-rubric.json")

    attestation = load_json(reviewer_path, f"{run_dir}: reviewer attestation", failures)
    if attestation is None:
        return result
    if attestation.get("schema_version") != "1.0" or attestation.get("attestation_type") != "human-review":
        failures.append(f"{run_dir}: reviewer attestation schema/type is invalid")
    if not is_safe_identifier(attestation.get("attestation_id"), 8):
        failures.append(f"{run_dir}: reviewer attestation needs a stable attestation_id")
    trigger = context.get("trigger") or {}
    if attestation.get("run_id") != trigger.get("run_id"):
        failures.append(f"{run_dir}: reviewer attestation run_id does not match trigger-run.json")

    reviewer = attestation.get("reviewer")
    if not isinstance(reviewer, dict):
        failures.append(f"{run_dir}: reviewer attestation needs reviewer identity fields")
        reviewer = {}
    reviewer_id = reviewer.get("id")
    reviewer_name = reviewer.get("display_name")
    reviewer_type = reviewer.get("type")
    if reviewer_type != "human" or not is_human_reviewer(reviewer_id) or not is_human_reviewer(reviewer_name):
        failures.append(f"{run_dir}: reviewer attestation must identify a non-anonymous human")
    if attestation.get("issuer_id") != reviewer_id:
        failures.append(f"{run_dir}: reviewer attestation issuer_id must equal reviewer.id")
    if notes_reviewer_id != reviewer_id or notes_reviewer != reviewer_name:
        failures.append(f"{run_dir}: reviewer-notes.md identity must match reviewer attestation")

    reviewed_at = require_timestamp(
        f"{run_dir}: reviewer attestation reviewed_at", attestation.get("reviewed_at"), failures, now
    )
    issued_at = require_timestamp(
        f"{run_dir}: reviewer attestation issued_at", attestation.get("issued_at"), failures, now
    )
    result["reviewed_at"] = reviewed_at
    result["issued_at"] = issued_at
    if notes_reviewed_at and reviewed_at and notes_reviewed_at != reviewed_at:
        failures.append(f"{run_dir}: reviewer-notes.md Reviewed at must match reviewer attestation")
    run_completed_at = context.get("run_completed_at")
    host_issued_at = (context.get("host") or {}).get("issued_at")
    for prior_label, prior in [
        ("both route completions", run_completed_at),
        ("host attestation", host_issued_at),
        ("validation", validation_at),
    ]:
        if reviewed_at and prior and reviewed_at < prior:
            failures.append(f"{run_dir}: human review must follow {prior_label}")
    if reviewed_at and issued_at and issued_at < reviewed_at:
        failures.append(f"{run_dir}: reviewer attestation issued_at must not precede reviewed_at")

    if attestation.get("rubric_sha256") != rubric.get("hash"):
        failures.append(f"{run_dir}: reviewer attestation is not bound to scoring-rubric.json")
    routes = context.get("routes") or {}
    outputs = attestation.get("outputs")
    expected_outputs = {
        name: routes.get(name, {}).get("output_sha256") for name in ROUTE_EXPECTATIONS
    }
    if outputs != expected_outputs:
        failures.append(f"{run_dir}: reviewer attestation output hashes do not match trigger-run.json")

    dimension_map = rubric.get("dimensions") or {}
    score_entries = attestation.get("dimension_scores")
    score_map: dict[str, dict[str, Any]] = {}
    without_total = 0
    with_total = 0
    if not isinstance(score_entries, list):
        failures.append(f"{run_dir}: reviewer attestation needs per-dimension scores")
    else:
        for entry in score_entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("dimension_id"), str):
                failures.append(f"{run_dir}: reviewer dimension score entry is invalid")
                continue
            key = normalize_identifier(entry["dimension_id"])
            if key in score_map:
                failures.append(f"{run_dir}: reviewer dimension scores must be unique")
                continue
            score_map[key] = entry
        if set(score_map) != set(dimension_map):
            failures.append(f"{run_dir}: reviewer must score every rubric dimension exactly once")
        for key, dimension in dimension_map.items():
            entry = score_map.get(key)
            if entry is None:
                continue
            weight = dimension["weight"]
            without_score = entry.get("without_score")
            with_score = entry.get("with_score")
            for label, score in [("without_score", without_score), ("with_score", with_score)]:
                if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= weight:
                    failures.append(
                        f"{run_dir}: reviewer dimension {dimension['id']!r} {label} must be 0..weight"
                    )
            if isinstance(without_score, int) and not isinstance(without_score, bool):
                without_total += without_score
            if isinstance(with_score, int) and not isinstance(with_score, bool):
                with_total += with_score
            validate_score_evidence_refs(
                run_dir,
                dimension["id"],
                entry.get("evidence_refs"),
                failures,
            )

    recalculated = {"without": without_total, "with": with_total, "delta": with_total - without_total}
    if attestation.get("totals") != recalculated:
        failures.append(f"{run_dir}: reviewer totals must be recomputed from per-dimension scores")
    notes_without, notes_with, notes_delta = parse_score(notes)
    if (notes_without, notes_with, notes_delta) != (
        recalculated["without"],
        recalculated["with"],
        recalculated["delta"],
    ):
        failures.append(f"{run_dir}: reviewer-notes.md totals must match recomputed dimension scores")
    if recalculated["delta"] < 4:
        failures.append(f"{run_dir}: score delta must be >= 4, got {recalculated['delta']}")
    if attestation.get("decision") != "accepted":
        failures.append(f"{run_dir}: reviewer attestation decision must be accepted")
    if (extract_field(notes, "Pass / partial / fail") or "").casefold() != "pass":
        failures.append(f"{run_dir}: reviewer outcome must be pass for release acceptance")
    if (extract_field(notes, "Human status") or "").casefold() != "accepted":
        failures.append(f"{run_dir}: Human status must be accepted")

    result["valid"] = len(failures) == before
    return result


def validate_run(run_dir: Path) -> list[str]:
    run_dir = run_dir.resolve()
    failures: list[str] = []
    now = datetime.now(timezone.utc)

    for rel, minimum in REQUIRED_TEXT_FILES.items():
        path = run_dir / rel
        if not path.exists():
            failures.append(f"{run_dir}: missing {rel}")
            continue
        text = read(path)
        if len(text.strip()) < minimum:
            failures.append(f"{run_dir}: {rel} is too thin")
        hits = placeholder_hits(text)
        if hits:
            failures.append(f"{run_dir}: {rel} still contains placeholder/unexecuted marker {hits[0]!r}")
        for phrase in REQUIRED_PHRASES.get(rel, []):
            if phrase.casefold() not in text.casefold():
                failures.append(f"{run_dir}: {rel} missing phrase {phrase!r}")

    for rel in REQUIRED_JSON_FILES:
        if not (run_dir / rel).exists():
            failures.append(f"{run_dir}: missing {rel}")

    input_path = run_dir / "input.md"
    prompt_without = run_dir / "prompt-without-skill.txt"
    prompt_with = run_dir / "prompt-with-skill.txt"
    if input_path.exists() and prompt_without.exists() and prompt_with.exists():
        input_text = read(input_path).strip()
        without_text = read(prompt_without).strip()
        with_text = read(prompt_with).strip()
        if without_text != with_text:
            failures.append(f"{run_dir}: clean-session prompts must be identical after trim")
        if input_text != without_text:
            failures.append(f"{run_dir}: prompt files must preserve input.md without hidden acceptance instructions")

    output_without = run_dir / "without-skill-output.md"
    output_with = run_dir / "with-skill-output.md"
    if output_without.exists() and output_with.exists() and sha256_file(output_without) == sha256_file(output_with):
        failures.append(f"{run_dir}: with/without outputs are identical")

    evidence_at: datetime | None = None
    evidence_path = run_dir / "evidence-sweep.md"
    if evidence_path.exists():
        evidence = read(evidence_path)
        evidence_at = require_timestamp(
            f"{run_dir}: evidence-sweep.md Evidence checked at",
            extract_field(evidence, "Evidence checked at"),
            failures,
            now,
        )
        evidence_refs = extract_field(evidence, "Evidence refs")
        if not evidence_refs or len(evidence_refs) < 12 or placeholder_hits(evidence_refs):
            failures.append(f"{run_dir}: evidence-sweep.md needs concrete Evidence refs")

    context = validate_trigger_run(run_dir, failures, now)
    rubric = validate_rubric(run_dir, failures, now, context.get("earliest_started_at"))

    capability_at: datetime | None = None
    capability_path = run_dir / "tool-capability.md"
    if capability_path.exists():
        capability = read(capability_path)
        capability_at = require_timestamp(
            f"{run_dir}: tool-capability.md Checked at",
            extract_field(capability, "Checked at"),
            failures,
            now,
        )
        for label in ["Host runtime", "Python command", "Skill invocation surface", "Evidence refs"]:
            value = extract_field(capability, label)
            if not value or len(value) < 3 or placeholder_hits(value):
                failures.append(f"{run_dir}: tool-capability.md field {label!r} lacks concrete evidence")
        attested_capabilities = (context.get("host") or {}).get("capabilities") or {}
        capability_bindings = {
            "Host runtime": "host_runtime",
            "Python command": "python_command",
            "Skill invocation surface": "skill_invocation_surface",
        }
        for label, field in capability_bindings.items():
            local_value = extract_field(capability, label)
            external_value = attested_capabilities.get(field)
            if not isinstance(local_value, str) or not isinstance(external_value, str) or normalize_identifier(local_value) != normalize_identifier(external_value):
                failures.append(f"{run_dir}: tool-capability.md {label} must match external host attestation")
        refs = extract_field(capability, "Evidence refs") or ""
        for required_ref in ["runtime-without-skill.log", "runtime-with-skill.log"]:
            if required_ref not in refs:
                failures.append(f"{run_dir}: tool-capability.md Evidence refs must include {required_ref}")
        host_ref = extract_field(capability, "Host attestation")
        if resolve_external_path(run_dir, host_ref) != (context.get("host") or {}).get("path"):
            failures.append(f"{run_dir}: tool-capability.md must reference the external host attestation")

    earliest = context.get("earliest_started_at")
    for label, timestamp in [("evidence sweep", evidence_at), ("tool capability check", capability_at), ("rubric freeze", rubric.get("frozen_at"))]:
        if earliest and timestamp and timestamp > earliest:
            failures.append(f"{run_dir}: {label} must be completed before either route starts")

    validation_at: datetime | None = None
    validation_path = run_dir / "validation.md"
    if validation_path.exists():
        validation = read(validation_path)
        if (extract_field(validation, "Validation status") or "").casefold() != "passed":
            failures.append(f"{run_dir}: validation.md Validation status must be passed")
        validation_at = require_timestamp(
            f"{run_dir}: validation.md Validation run at",
            extract_field(validation, "Validation run at"),
            failures,
            now,
        )
        result_ref = extract_field(validation, "Result evidence")
        result_path = resolve_internal_path(run_dir, result_ref)
        if result_path is None or result_path.name != "validation.log" or not result_path.is_file():
            failures.append(f"{run_dir}: validation.md Result evidence must point to validation.log")
        elif extract_field(validation, "Validation log SHA-256") != sha256_file(result_path):
            failures.append(f"{run_dir}: validation.md Validation log SHA-256 does not match validation.log")
        if result_path and result_path.is_file():
            log_text = read(result_path)
            if extract_field(log_text, "Command exit code") != "0":
                failures.append(f"{run_dir}: validation.log must record Command exit code: 0")
            log_completed = require_timestamp(
                f"{run_dir}: validation.log Completed at",
                extract_field(log_text, "Completed at"),
                failures,
                now,
            )
            if log_completed and validation_at and log_completed != validation_at:
                failures.append(f"{run_dir}: validation.log Completed at must match Validation run at")
            source_snapshot = extract_field(log_text, "Source snapshot") or ""
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", source_snapshot, re.I):
                failures.append(f"{run_dir}: validation.log Source snapshot must be a SHA-256 identifier")
    run_completed_at = context.get("run_completed_at")
    if run_completed_at and validation_at and validation_at < run_completed_at:
        failures.append(f"{run_dir}: validation must follow both route completions")

    notes_path = run_dir / "reviewer-notes.md"
    notes = read(notes_path) if notes_path.exists() else ""
    reviewer = validate_reviewer_attestation(
        run_dir, notes, context, rubric, validation_at, failures, now
    )

    release_path = run_dir / "release-gate.md"
    if release_path.exists():
        release = read(release_path)
        structure_status = (extract_field(release, "Structure status") or "").casefold()
        runtime_status = (extract_field(release, "Runtime status") or "").casefold()
        human_status = (extract_field(release, "Human status") or "").casefold()
        ready = (extract_field(release, "Ready decision") or "").casefold()
        if structure_status != "artifact_consistent":
            failures.append(f"{run_dir}: Structure status must be artifact_consistent, not a runtime claim")
        if runtime_status == "verified" and not (context.get("host") or {}).get("valid"):
            failures.append(f"{run_dir}: Runtime status cannot be verified without a valid external host anchor")
        if runtime_status != "verified":
            failures.append(f"{run_dir}: Runtime status must be verified for Ready decision: pass")
        if human_status == "verified" and not reviewer.get("valid"):
            failures.append(f"{run_dir}: Human status cannot be verified without a valid external reviewer attestation")
        if human_status != "verified":
            failures.append(f"{run_dir}: Human status must be verified for Ready decision: pass")
        if ready != "pass":
            failures.append(f"{run_dir}: Ready decision must be pass only after all three evidence layers close")
        if ready == "pass" and (not (context.get("host") or {}).get("valid") or not reviewer.get("valid")):
            failures.append(f"{run_dir}: Ready decision cannot pass on self-reported run-folder evidence")

        release_at = require_timestamp(
            f"{run_dir}: release-gate.md Release decided at",
            extract_field(release, "Release decided at"),
            failures,
            now,
        )
        for prior_label, prior in [
            ("host attestation", (context.get("host") or {}).get("issued_at")),
            ("validation", validation_at),
            ("reviewer attestation", reviewer.get("issued_at")),
        ]:
            if release_at and prior and release_at < prior:
                failures.append(f"{run_dir}: release decision must follow {prior_label}")
        expected_hashes = {
            "Host attestation SHA-256": (context.get("host") or {}).get("sha256"),
            "Reviewer attestation SHA-256": reviewer.get("sha256"),
            "Rubric SHA-256": rubric.get("hash"),
        }
        for label, expected in expected_hashes.items():
            if extract_field(release, label) != expected:
                failures.append(f"{run_dir}: release-gate.md {label} does not match bound evidence")

    return failures


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python scripts/check_acceptance_runs.py <run_dir> [<run_dir> ...]")
        return 2

    failures: list[str] = []
    for arg in sys.argv[1:]:
        run_dir = Path(arg)
        if not run_dir.exists():
            failures.append(f"missing run dir: {run_dir.resolve()}")
            continue
        failures.extend(validate_run(run_dir))

    if failures:
        print("Acceptance run check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Acceptance run check passed.")
    print(
        f"Checked {len(sys.argv) - 1} completed run folder(s): "
        "structure=artifact_consistent, runtime=verified, human=verified, ready=pass."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
