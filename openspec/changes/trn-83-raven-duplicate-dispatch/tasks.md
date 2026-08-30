## 1. Raven prompt update

- [ ] 1.1 Add pre-dispatch deduplication checklist to `academy/agents/raven.json` system prompt:
  - Before dispatching any persona, check spawn list for an existing task for that persona
  - If `done=false` → steer it, don't spawn new
  - If `done=true, outcome=completed` → persona finished, proceed to next step
  - If `done=true, outcome=failed` (timeout) → check tasks.md for last completed task, dispatch continuation starting from there
  - If `done=true, outcome=stopped` (AcpProcessDied) → retry from last checked task in tasks.md, same as timeout
- [ ] 1.2 Add stale mail clarification: unread mail in a persona's mailbox is NOT a signal that persona is in flight — only spawn list is authoritative for in-flight state

## 2. STANDING_ORDERS.md update

- [ ] 2.1 Strengthen "Avoid duplicate dispatches" section with the three-layer check pattern (raven mailbox → spawn list task descriptions → agent field)
- [ ] 2.2 Add explicit `AcpProcessDied` guidance: `outcome=stopped` means process died, treat as failed/retry — NOT as completed
- [ ] 2.3 Add timeout guidance: `outcome=failed` with timeout error means partial progress — check tasks.md before dispatching continuation
- [ ] 2.4 Clarify stale mail semantics: mail in `new/` from a prior dispatch is historical record, not in-flight signal

## 3. sdd.md update

- [ ] 3.1 Add intent UUID idempotency check to the SDD dispatch protocol: on each captain check-in, scan spawn list task descriptions for the current intent UUID before dispatching; if found, steer or continue rather than spawn new

## 4. Verification

- [ ] 4.1 Run an SDD crew (any change), observe captain cron behaviour — verify no duplicate dispatches occur across multiple 5-min ticks
- [ ] 4.2 Simulate a timeout: let Ghost time out, verify Raven on the next tick correctly identifies partial progress and dispatches a continuation rather than starting from scratch
