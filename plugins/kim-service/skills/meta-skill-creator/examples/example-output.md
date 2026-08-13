# Example Output: Skill Design Board

## Domain Research Brief

- Raw user intent: "make a customer-support follow-up skill from scattered notes."
- Suspected domain: customer support follow-up and internal handoff.
- Confidence: medium-high after support workflow examples, escalation rules, and privacy boundaries are reviewed.
- Users / roles: support agent, account owner, operations lead, or service manager.
- Pressure moment: customer history is scattered, tone must be careful, and the next owner needs enough context to act.
- Native artifacts: customer-facing reply, internal handoff checklist, escalation decision, missing-information list, and validation manifest.
- Work surface: text response plus structured checklist file.
- Must not simulate: fake commitments, fake approvals, unverified resolution status, or private customer data not present in the input.
- Decision: make skill; publish only after baseline evidence and a clean acceptance run are tested.

## Deep Research Decision

- Intensity: minimum sweep for the local design candidate; upgrade to deep research before public compatibility or platform-rule claims.
- Decision at stake: whether support follow-up has a stable workflow and artifact chain worth packaging.
- Source hierarchy: user records and policy first, then official platform rules, maintained workflow examples, failure discussions, and counterevidence.
- Decision impact: evidence determines privacy boundaries, escalation steps, mandatory fields, and release tests.
- Stop rule: stop the minimum sweep when workflow and failure modes are supported; return `research-needed` if policy or platform behavior remains uncertain.

## Skillization Decision

- Decision: make skill.
- Reason: high-frequency workflow, stable input/output shape, repeatable package structure, and ordinary prompts often stop at a reply draft without handoff or escalation checks.

## User Result

- User: support operator handling scattered customer context.
- Final artifact: sendable reply, internal handoff checklist, escalation recommendation, and validation manifest.
- Three-minute visible result: first reply draft plus risk/missing-info checklist.
- Success: every customer-facing claim is grounded, owner/next action are explicit, and unresolved facts remain visible.
- Non-goal: deciding compensation, promising resolution, or changing customer/account state.

## Goal Contract

When support context is scattered and a handoff is urgent, produce a grounded reply and an actionable internal handoff package; completion requires factual traceability, an explicit owner/next action, and visible unresolved risks.

## Execution Contract

1. Enter with source notes; extract facts, uncertainties, commitments, and private fields; output a traceable fact table; stop if the source is unreadable.
2. Enter with the fact table; classify response, handoff, and escalation needs; output the selected route and rationale; request authority if the route changes customer/account state.
3. Enter with the selected route; draft the reply and handoff checklist; output customer-facing and internal artifacts; return to step 1 if a claim lacks evidence.
4. Enter with both artifacts; run privacy, ownership, next-action, and completeness checks; output validation status; release only when all required checks pass.

## Boundary Contract

- Scope: support follow-up and internal handoff; not general CRM automation.
- Truth: only source-backed facts may appear as facts; unresolved information stays marked unknown.
- Authority: no refunds, compensation, account changes, external sending, or publishing without explicit authority.
- Side effects: candidate generation is file/text only; external systems remain unchanged.
- Stop: stop on unreadable input, missing authority, policy conflict, or unsupported commitment.
- Fallback: provide a partial draft plus missing-information list; do not claim ready.

## Core Mechanism

Use a `support-follow-up-workbench`: convert scattered notes into facts, uncertainties, customer-facing language, owner handoff, escalation rule, and validation checks.

## Package Plan

这是当前客服跟进案例按其失败模式选择的包计划，不是其他候选 Skill 的必选文件清单。

```text
support-follow-up-skill/
  SKILL.md
  references/domain-rules.md
  references/tone-and-escalation.md
  references/failure-modes.md
  scripts/validate-follow-up.py
  assets/follow-up-brief-template.md
  examples/example-input.md
  examples/example-output.md
  evals/trigger-eval.json
  evals/output-eval.md
  evals/baseline-compare.md
  verification-summary.md
```

## Required Evals

- Trigger eval: should trigger on reusable support follow-up package requests; should not trigger on one-off reply polishing.
- Output eval: missing facts, angry customer, conflicting internal notes, privacy-sensitive details, and escalation uncertainty.
- Baseline: compare ordinary prompt reply against skill-produced reply plus handoff checklist.
- Regression: previous version versus new version on factual grounding, tone, escalation, and missing-info handling.

## Release Gate Status

- Structure: planned.
- Trigger: not run.
- Output: not run.
- Baseline: not run.
- Acceptance: not run.
- Evidence status: design candidate; publish after clean-session acceptance and baseline proof.
