# Changelog

## Kim Service V1.0 - 2026-07-15

- Preserved `KimYx0207/agent-teams-playbook` revision `753ff43bd9b1f9aee4d184c4f21e7f494af5a79f` as the repository history base.
- Published the playbook as a self-contained component under `skills/agent-teams-playbook` while repository-level releases move to the Kim Service version line.

## [4.8.0] - 2026-07-10

### Fixed

- Replaced the mandatory Skill fallback ritual with stop-on-match capability resolution. Existing local Agents, Skills, Tools, Commands, and MCP providers now win immediately; external discovery runs only for a proven gap, and degraded mode requires a real host, permission, or owner failure.
- Added explicit native contracts for both primary runtimes: Claude Code keeps its `Agent` / `Task` and optional Team surfaces, while Codex uses only top-level `spawn_agent(task_name, message, fork_turns)` without legacy typed/namespaced fallback.
- Recorded the live Claude Code Agent schema requirement that `prompt` is mandatory; owner/type/name fields do not replace the worker prompt.

### Added

- Added runtime-native skill package directories for Claude Code and Codex:
  `.claude/skills/agent-teams-playbook/` and `.agents/skills/agent-teams-playbook/`.
- Added Codex config metadata in `.codex/config.toml`.
- Added `NOTICE` for release and package metadata.

### Changed

- Updated the install script to prefer the target runtime package directory when
  installing locally or from GitHub, while keeping the root `SKILL.md` fallback
  for runtimes without a dedicated package tree.

### Verification

- `node --test tests/runtime-contracts.test.mjs`
- `bash -n scripts/install.sh`
- Live Claude Code `2.1.196` regression: one Skill call and one Agent call with the required `prompt`, no retry.
- Codex task evidence: three successful native top-level `spawn_agent` calls.
