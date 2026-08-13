# Changelog

This component follows the repository-level Kim Service version and tags.

## V1.0 - 2026-07-15

- Published from the canonical `skills/memory-3layer` package; Kim Service records the exact direct-sync tree revision in its root catalog and release changelog.
- Renamed the public component from `claude-memory-3layer` to platform-neutral `memory-3layer`.
- Moved the default data root from `.claude/memory/` to `.memory-3layer/` and added a non-destructive legacy migration path.
- Added shared-core adapters for Claude Code and Codex while keeping other Agent Skills hosts on an explicit manual route.
- Added Codex Hook review/trust instructions and separated artifact, adapter, and runtime evidence.
- Replaced product-specific metadata with Agent Skills standard frontmatter.
- Defined goal, step, transition, failure, and six-boundary contracts.
- Standardized public README image alignment and support-code layout.

## Historical import — 2026-07-14

- Imported `KimYx0207/claude-memory-3layer` revision `1d60800c1a34dfe83d8e2b102b24c7d57d87ca53` as the historical base.
