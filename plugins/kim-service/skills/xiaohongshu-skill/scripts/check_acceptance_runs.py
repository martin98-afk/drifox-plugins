#!/usr/bin/env python3
"""Validate Xiaohongshu skill acceptance run folders."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REQUIRED_FILES = [
    "input.md",
    "evidence-sweep.md",
    "without-skill-output.md",
    "with-skill-output.md",
    "reviewer-notes.md",
    "release-gate.md",
    "validation.md",
]

REQUIRED_PHRASES = {
    "evidence-sweep.md": ["User material", "Local / Graphify", "Host", "MCP", "Counterevidence"],
    "with-skill-output.md": ["标题", "正文", "标签", "图片"],
    "reviewer-notes.md": ["Score summary", "Without-skill", "With-skill", "Delta", "Pass / partial / fail"],
    "release-gate.md": ["Structure", "Domain research", "Baseline", "Ready decision"],
    "validation.md": ["Validation", "Result"],
}

WORKBENCH_HEADINGS = [
    "策略补全与决策提醒",
    "任务判断",
    "真人细节补位",
    "选题角度",
    "封面字",
    "图文页脚本",
    "视觉类型判断",
    "图片生成与配图提示词",
    "封面视觉验证",
    "批量图片生产",
    "标题",
    "正文草稿",
    "评论与私信承接",
    "标签建议",
    "最终成品自检",
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_score(text: str) -> tuple[int | None, int | None, int | None]:
    without = with_skill = delta = None
    for label, var in [(r"Without-skill", "without"), (r"With-skill", "with"), (r"Delta", "delta")]:
        match = re.search(label + r"\s*[:=]\s*(-?\d+)", text, re.I)
        if not match:
            continue
        value = int(match.group(1))
        if var == "without":
            without = value
        elif var == "with":
            with_skill = value
        else:
            delta = value
    if delta is None and without is not None and with_skill is not None:
        delta = with_skill - without
    return without, with_skill, delta


def validate_run(run_dir: Path) -> list[str]:
    failures: list[str] = []
    for rel in REQUIRED_FILES:
        path = run_dir / rel
        if not path.exists():
            failures.append(f"{run_dir}: missing {rel}")
            continue
        text = read(path)
        if len(text.strip()) < 120:
            failures.append(f"{run_dir}: {rel} is too thin")
        for phrase in REQUIRED_PHRASES.get(rel, []):
            if phrase.lower() not in text.lower():
                failures.append(f"{run_dir}: {rel} missing phrase {phrase!r}")

    notes = run_dir / "reviewer-notes.md"
    if notes.exists():
        without, with_skill, delta = parse_score(read(notes))
        if without is None or with_skill is None or delta is None:
            failures.append(f"{run_dir}: reviewer-notes.md missing parseable scores")
        elif delta < 4:
            failures.append(f"{run_dir}: score delta must be >= 4, got {delta}")

    release = run_dir / "release-gate.md"
    if release.exists():
        release_text = read(release).lower()
        if "ready decision: pass" not in release_text and "ready decision: partial" not in release_text:
            failures.append(f"{run_dir}: release-gate.md needs Ready decision: pass or partial")

    with_skill = run_dir / "with-skill-output.md"
    if with_skill.exists():
        output_text = read(with_skill)
        workbench_count = sum(1 for heading in WORKBENCH_HEADINGS if heading in output_text)
        if workbench_count >= 6 and "用户明确要求完整工作台" not in output_text and "allow_workbench_dump" not in output_text:
            failures.append(f"{run_dir}: with-skill-output.md looks like workbench dump, not final chat delivery")
        if re.search(r"这次要做到哪一步|做到哪一步|是否只要文案|要不要先停在脚本", output_text):
            if not re.search(r"用户明确只要文案|用户明确先不生成图片|explicit_text_only_request|text_only_requested|用户主动表达不确定", output_text):
                failures.append(f"{run_dir}: with-skill-output.md asks a scope-downgrade question after a generation intent")
        if re.search(r"文案\s*\+\s*脚本[\s\S]{0,40}推荐[\s\S]{0,80}不生成图片|推荐[\s\S]{0,40}文案\s*\+\s*脚本[\s\S]{0,80}不生成图片", output_text):
            if not re.search(r"用户明确只要文案|用户明确先不生成图片|explicit_text_only_request|text_only_requested", output_text):
                failures.append(f"{run_dir}: with-skill-output.md recommends text/script instead of full image generation")
        if re.search(r"不需要制作图片|只输出可(?:直接)?发布.*文案|只输出文案|不生成图片", output_text):
            if not re.search(r"用户明确只要文案|用户明确先不生成图片|explicit_text_only_request|text_only_requested|blocked|partial|阻塞|未生成实图", output_text):
                failures.append(f"{run_dir}: with-skill-output.md treats non-user text-only scope as execution boundary")
        if re.search(r"本地(?:其实|已经)?有一套|已有一套同题|历史输出|旧输出|旧图|旧包|复用旧|复用历史|以前生成|上次生成", output_text, re.I):
            if not re.search(r"用户明确要求复用|explicit_reuse_permission|reuse_requested|按用户要求复用", output_text, re.I):
                failures.append(f"{run_dir}: with-skill-output.md reuses old artifacts without explicit reuse permission")

    return failures


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: check_acceptance_runs.py <run_dir> [<run_dir> ...]")
        return 2
    failures: list[str] = []
    for arg in sys.argv[1:]:
        run_dir = Path(arg).resolve()
        if not run_dir.exists():
            failures.append(f"missing run dir: {run_dir}")
            continue
        failures.extend(validate_run(run_dir))
    if failures:
        print("Acceptance run check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Acceptance run check passed.")
    print(f"Checked {len(sys.argv) - 1} run folder(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
