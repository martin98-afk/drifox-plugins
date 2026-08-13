#!/usr/bin/env python3
"""校验 meta-skill-creator 风格的 Skill 包。

这个本地门禁用来防止只有文案、没有契约和验收的包。它要求包里包含
领域研究、产品设计、契约、模板、评测和示例，但不等于真实用户质量证明。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Windows 控制台默认 GBK，强制 UTF-8 输出避免中文乱码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REQUIRED_FILES = [
    "SKILL.md",
    "references/intent-domain-research.md",
    "references/experience-surface-model.md",
    "references/product-design.md",
    "references/skill-contract.md",
    "references/evidence.md",
    "references/source-abstraction-boundary.md",
    "references/multimodal-tooling.md",
    "references/release-gate.md",
    "references/evaluation-method.md",
    "references/closed-loop-governance.md",
    "assets/domain-research-brief-template.md",
    "assets/skill-contract-template.md",
    "assets/package-plan-template.md",
    "assets/product-design-board-template.md",
    "assets/multimodal-prompt-brief-template.md",
    "assets/acceptance-run-template.md",
    "assets/trigger-run-record-template.json",
    "assets/host-event-anchor-template.json",
    "assets/host-attestation-template.json",
    "assets/reviewer-attestation-template.json",
    "assets/loop-run-record-template.md",
    "evals/trigger-eval.json",
    "scripts/check_acceptance_runs.py",
    "scripts/prepare_acceptance_run.py",
    "scripts/test_acceptance_runs.py",
    "scripts/run-acceptance.sh",
    "scripts/run-baseline.sh",
    "scripts/check_closed_loop.py",
    "examples/example-input.md",
    "examples/example-output.md",
]

KEY_PHRASES = {
    "SKILL.md": ["意图与领域研究", "领域研究简报", "research-needed", "Fetch", "执行步骤契约", "Abstract Deep Research Protocol", "基线", "触发评测", "包计划", "发布门禁", "本地能力清单", "多模态简报", "闭环治理", "运行记录", "none-with-reason", "prepare_acceptance_run.py", "structure_status", "runtime_status", "human_status"],
    "references/intent-domain-research.md": ["Research Intensity", "Abstract Deep Research Protocol", "Decision at stake", "Source hierarchy", "Contradiction handling", "Decision impact", "Stop rule", "No Guessing Rule", "Domain Research Brief", "Fetch Before", "Network Research Gate", "Online evidence read", "research-needed", "Research-To-Design Chain", "Local capability inventory"],
    "references/experience-surface-model.md": ["Artifact Chain", "Surface After Domain Research", "worked example", "Local Capability Inventory"],
    "references/product-design.md": ["3 分钟可见结果", "体验流程设计", "例子不是元规则", "当前边界", "先做意图领域研究", "Local Capability", "Multimodal", "Loop Closure Board", "最终交付不是固定文件清单", "core / conditional / release", "目录数量不是完成标准"],
    "references/skill-contract.md": ["Goal Clarity Standard", "Domain Research Contract", "Execution Contract", "Boundary Completeness Standard", "Experience Surface Contract", "Trigger Contract", "Eval Contract", "Boundary Contract", "Local Capability / Multimodal Contract", "最小充分包", "不要建立空目录", "core / conditional / release"],
    "references/multimodal-tooling.md": ["Capability Inventory", "Multimodal Brief Contract", "Route Selection Rule", "Output evidence", "Image2 / host-native", "Downgrade proof"],
    "references/release-gate.md": ["发布门禁", "十四项门禁", "证据扫查", "验收运行记录", "就绪规则", "闭环", "none-with-reason", "trigger-run.json", "structure_status", "runtime_status", "human_status", "pending"],
    "references/closed-loop-governance.md": ["闭环定义", "原创循环", "阶段契约", "写回决策", "证据分层", "漂移信号", "原创边界", "nextRunReuseKey"],
    "assets/domain-research-brief-template.md": ["原始意图", "领域假设", "深度研究契约", "研究强度", "研究问题", "来源层级", "冲突证据处理", "Decision Impact", "停止规则", "技能化决定", "本地能力清单"],
    "assets/package-plan-template.md": ["这不是默认目录树", "core / conditional / release", "未命中条件的模块不创建", "具体消费者", "最小文件地图"],
    "assets/skill-contract-template.md": ["目标清晰度", "执行步骤契约", "边界完整性", "深度研究契约"],
    "assets/multimodal-prompt-brief-template.md": ["能力清单", "产物简报", "提示词变体", "验证"],
    "assets/acceptance-run-template.md": ["运行类型", "真实触发与运行记录", "读取与能力边界", "校验命令", "三层状态", "structure_status", "runtime_status", "human_status"],
    "assets/trigger-run-record-template.json": ["without-skill", "with-skill", "execution_status", "prompt_sha256", "output_sha256", "trigger_observed", "evidence_files", "attestations"],
    "assets/host-event-anchor-template.json": ["host-session-export", "event_id", "captured_at", "prompt_sha256", "output_sha256"],
    "assets/host-attestation-template.json": ["host-runtime", "attestation_id", "capabilities", "event_anchor", "routes"],
    "assets/reviewer-attestation-template.json": ["human-review", "reviewer", "rubric_sha256", "dimension_scores", "evidence_refs", "totals"],
    "assets/loop-run-record-template.md": ["Intent Core", "Evidence Fetch", "Product Surface", "Package Contract", "Verification Evidence", "Loop Decision", "Scar Record", "next_run_reuse_key"],
    "scripts/check_acceptance_runs.py": ["REQUIRED_TEXT_FILES", "Goal Contract", "Execution Contract", "Boundary Contract", "Deep Research Decision", "normalize_identifier", "external host attestation", "per-dimension scores", "artifact_consistent", "Acceptance run check"],
    "scripts/prepare_acceptance_run.py": ["status remains", "pending", "No model run", "Goal Contract", "Execution Contract", "Boundary Contract", "Deep Research Decision", "trigger-run.json", "tool-capability.md"],
    "scripts/test_acceptance_runs.py": ["positive", "negative", "missing-capability", "alternate-fixed-totals", "same-session-space", "generic-placeholder", "ai-reviewer", "coordinated-internal-rewrite", "Acceptance validator regression passed"],
    "scripts/run-acceptance.sh": ["prepare_acceptance_run.py", "--mode acceptance"],
    "scripts/run-baseline.sh": ["prepare_acceptance_run.py", "--mode baseline"],
    "scripts/check_closed_loop.py": ["REQUIRED_FILES", "BANNED_EXTERNAL_MARKERS", "Closed-loop check"],
    "references/evidence.md": ["Evidence Card Shape", "Online Evidence Standard", "Source Map", "Key Findings", "Write-In Decision", "none-with-reason"],
    "references/evaluation-method.md": ["Contract Clarity Gate", "Goal unclear", "Execution step opaque", "Boundary incomplete", "Deep research ritualized", "Unknown Domain Research Test", "research-needed", "Domain Research Brief", "Multimodal Tool Route Regression", "No Domain Research Brief", "Surface guessed", "baseline", "Domain Research", "multimodal", "Loop Closure", "trigger-run.json", "structure_status", "runtime_status", "human_status", "test_acceptance_runs.py"],
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip().strip('"')
    return fields


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    root = root.resolve()
    failures: list[str] = []

    for rel in REQUIRED_FILES:
        if not (root / rel).exists():
            failures.append(f"缺少必需文件：{rel}")

    skill_path = root / "SKILL.md"
    if skill_path.exists():
        skill = read(skill_path)
        fm = parse_frontmatter(skill)
        if fm.get("name") != root.name:
            failures.append("SKILL.md frontmatter 的 name 必须与目录名一致")
        desc = fm.get("description", "")
        if len(desc) < 120:
            failures.append("SKILL.md description 太弱，无法稳定路由触发")
        if len(skill.splitlines()) > 500:
            failures.append("SKILL.md 应低于 500 行；细节应移动到 references")

    trigger_path = root / "evals/trigger-eval.json"
    if trigger_path.exists():
        data = json.loads(read(trigger_path))
        cases = data.get("cases", [])
        counts: dict[str, int] = {}
        for case in cases:
            case_type = case.get("type", "unknown")
            counts[case_type] = counts.get(case_type, 0) + 1
        expected = {"should-trigger": 5, "should-not-trigger": 5, "near-miss": 3, "ambiguous": 3}
        for case_type, minimum in expected.items():
            if counts.get(case_type, 0) < minimum:
                failures.append(f"触发评测至少需要 {minimum} 个 {case_type} 用例")

    trigger_record_path = root / "assets/trigger-run-record-template.json"
    if trigger_record_path.exists():
        try:
            trigger_record = json.loads(read(trigger_record_path))
        except json.JSONDecodeError as exc:
            failures.append(f"assets/trigger-run-record-template.json 不是有效 JSON：{exc}")
        else:
            routes = trigger_record.get("routes", [])
            route_names = {route.get("route") for route in routes if isinstance(route, dict)}
            if route_names != {"without-skill", "with-skill"}:
                failures.append("trigger-run 模板必须且只能包含 without-skill / with-skill 两条 route")
            if trigger_record.get("status") != "pending":
                failures.append("trigger-run 模板的 status 必须保持 pending")
            if trigger_record.get("schema_version") != "2.0":
                failures.append("trigger-run 模板 schema_version 必须为 2.0")
            attestations = trigger_record.get("attestations")
            if not isinstance(attestations, dict) or set(attestations) != {"host", "reviewer"}:
                failures.append("trigger-run 模板必须声明目录外 host / reviewer attestations")

    for runner_rel in ["scripts/run-acceptance.sh", "scripts/run-baseline.sh"]:
        runner_path = root / runner_rel
        if not runner_path.exists():
            continue
        runner_text = read(runner_path)
        for banned in ["Without-skill: 35", "With-skill: 88", "Delta: 53", "Ready decision: pass", "cat >"]:
            if banned in runner_text:
                failures.append(f"{runner_rel} 不得预填验收结果：{banned}")
        if "prepare_acceptance_run.py" not in runner_text:
            failures.append(f"{runner_rel} 必须只包装跨平台 Python 准备入口")

    for rel, phrases in KEY_PHRASES.items():
        path = root / rel
        if not path.exists():
            continue
        text = read(path).lower()
        for phrase in phrases:
            if phrase.lower() not in text:
                failures.append(f"{rel} 缺少关键短语：{phrase}")

    product_design_path = root / "references/product-design.md"
    if product_design_path.exists():
        product_design = read(product_design_path)
        if re.search(r"候选\s*skill\s*包[^\n]{0,20}至少包含", product_design, re.I):
            failures.append("references/product-design.md 不得把候选 Skill 写成固定必选文件清单")

    fixed_package_patterns = {
        "references/skill-contract.md": [
            r"完整候选包[^\n]*(?:references/|assets/|scripts/)[^\n]*(?:evals/|examples/)",
        ],
        "assets/package-plan-template.md": [
            r"<skill>/\s*\n\s*SKILL\.md\s*\n\s*references/",
        ],
    }
    for rel, patterns in fixed_package_patterns.items():
        path = root / rel
        if not path.exists():
            continue
        content = read(path)
        for pattern in patterns:
            if re.search(pattern, content, re.I | re.S):
                failures.append(f"{rel} 不得把可选模块写成默认全套目录")

    if failures:
        print("Meta skill package check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Meta skill package check passed.")
    print(f"已检查 {len(REQUIRED_FILES)} 个必需文件：{root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
