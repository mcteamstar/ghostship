## Why

Raven dispatches duplicate agent tasks when the captain cron fires multiple times while a prior dispatch is still in flight — observed on TRN-74, TRN-76, TRN-78, and TRN-71. The duplicates cause `AcpProcessDied` crashes, corrupt shared state (two tasks checking off the same boxes in tasks.md), and require manual Admiral intervention to untangle.

## What Changes

- **`academy/agents/raven.json`** — add explicit pre-dispatch deduplication instruction to the Raven prompt: before dispatching any persona, check the spawn list and verify no task for that persona is already running or recently completed; if one is, steer or continue it instead
- **`academy/steering/STANDING_ORDERS.md`** — strengthen the "Avoid duplicate dispatches" section with the concrete three-layer check pattern (Raven mailbox → spawn list task description → agent field) and explicit handling for the `AcpProcessDied` case (task stopped ≠ task succeeded — verify before treating as done)
- **`academy/orders/sdd.md`** — tighten the SDD intent token protocol: the intent UUID written to Raven's mailbox before dispatch is the idempotency key; Raven must check for an existing task matching that intent UUID in the spawn list before spawning a new one

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None — prompt and steering changes only. No transport code changes. No spec-level behaviour changes.

## Impact

- `academy/agents/raven.json` — Raven system prompt
- `academy/steering/STANDING_ORDERS.md` — crew-wide standing guidance
- `academy/orders/sdd.md` — SDD captain order template
- No changes to `transport/`, tests, or docs
