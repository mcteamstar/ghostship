## Context

See proposal.md — Why.

**Observed failure pattern (TRN-71 session):**
1. Captain cron fires, Raven dispatches Ghost with intent UUID written to raven mailbox
2. Ghost times out at 60 min, task recorded as `failed`
3. Captain cron fires again, Raven sees stale unread mails in ghost mailbox from prior dispatch
4. Raven reads `done=false` on the failed task but doesn't check `outcome` field — treats as still-in-flight
5. OR: Raven sees no running ghost task and dispatches fresh, but the stale intent mails cause confusion about which dispatch is current
6. Additionally: `AcpProcessDied` sets `outcome=stopped` — Raven has no explicit guidance to distinguish this from a clean completion

**Current Raven prompt — what's missing:**
The prompt says "dispatch, steer, or continue" but gives no explicit pre-dispatch checklist. It relies on the `STANDING_ORDERS.md` section "Avoid duplicate dispatches" which is generic guidance without the specific mechanism.

**Current STANDING_ORDERS.md — what's missing:**
The section exists but only says "check spawn list before dispatching." It doesn't cover:
- What to do when a task shows `outcome=stopped` (AcpProcessDied) vs `outcome=completed`
- What to do when a task shows `done=true` but `outcome=failed` (timeout)
- The three-layer check (mailbox → task description → agent field)
- The stale mail problem: unread mails in ghost's mailbox from a prior failed dispatch are NOT a signal that ghost is in flight

## Goals / Non-Goals

**Goals:** Eliminate duplicate dispatches in normal SDD operation. Give Raven explicit rules for the `AcpProcessDied` and timeout cases. Clarify stale mail semantics.

**Non-Goals:** Transport-level deduplication (would require TRN-83 to extend the spawn API). Eliminating all possible duplicate scenarios (only SDD-pattern dispatches are in scope).

## Decisions

### Three-layer check before any dispatch

**Decision:** Before dispatching a persona, Raven checks in this order:
1. **Raven mailbox** (primary) — look for a `dispatching <persona> <task_id>` message in `raven/new/` and `raven/cur/`. If found and the task is not yet `done=true`, hold.
2. **Spawn list task descriptions** (secondary) — scan `kirocrew spawn list` for any task whose description mentions the persona name. Catches cases where the mailbox record was lost.
3. **Agent field** (tertiary) — only reliable once KiroCrew has assigned the persona; use as confirmation, not primary signal.

If all three are clear, dispatch is safe.

### Stale mail ≠ in-flight

**Decision:** Add explicit guidance: unread mail in a persona's mailbox (e.g. ghost's `new/` folder) does NOT indicate that persona is in flight. Mail accumulates from prior dispatches and is only cleared by the agent itself. The only reliable in-flight signal is `spawn list`.

### AcpProcessDied handling

**Decision:** `outcome=stopped` with error containing `AcpProcessDied` means the runtime process died — NOT a successful completion. Raven must treat this the same as `outcome=failed`: the task needs to be retried from the last known good state (check tasks.md for the last checked task), not assumed complete.

### Timeout handling

**Decision:** `outcome=failed` with a timeout error means the task ran out of time but may have made partial progress. Raven must check tasks.md to see what was completed before dispatching a continuation, so the new dispatch starts from the right place rather than from scratch.

### sdd.md intent token as idempotency key

**Decision:** The intent UUID written to the raven mailbox before dispatch is the canonical idempotency key. On each captain check-in, Raven checks whether a task matching the current intent UUID already exists in the spawn list (by scanning task descriptions for the UUID). If it does — regardless of state — no new dispatch is needed; steer or continue the existing task instead.

## Risks / Trade-offs

- Prompt changes are harder to verify than code changes — the only test is running a crew and observing behaviour.
- The three-layer check adds a few extra shell commands per Raven run. Negligible cost.
- Stricter deduplication may cause Raven to "hold" when it should retry a genuinely dead task. Mitigation: the `AcpProcessDied` rule explicitly says to retry in that case.

## Migration Plan

No migration. Academy changes take effect on the next `./install.sh` run (which copies `academy/` into the data volume).
