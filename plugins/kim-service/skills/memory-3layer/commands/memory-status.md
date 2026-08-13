---
name: memory-status
description: Show platform-neutral three-layer memory statistics and runtime evidence
version: 1.0.0
---

# Memory Status

Use `MEMORY_DIR` when set; otherwise inspect `<repo>/.memory-3layer/`. Treat
`<repo>/.claude/memory/` only when `MEMORY_LEGACY_READ=1` was explicitly enabled; it is never the destination
for a new write.

Report:

1. Layer 1 topic count, active/superseded item counts, and newest timestamp.
2. Layer 2 note count and date range.
3. Layer 3 line/section count and modified time.
4. `data/session_state.json` status and most recent compact counter.
5. Whether runtime execution was actually observed. Configuration files alone
   are `configured`, not proof that a host trusted and invoked the hooks.

Use the user's language. Include the resolved memory root, skipped invalid JSON,
and one concrete next action. Never print secret-looking values or raw payloads.
