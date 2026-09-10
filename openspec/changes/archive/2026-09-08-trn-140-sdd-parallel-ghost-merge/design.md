## Context

See proposal.md for motivation.

The Reconciliation phase in `academy/orders/sdd.md` currently tells Ghost:
1. Merge each branch with `git merge --no-ff`
2. Run `bash tests/run.sh --unit`
3. On success → mail Admiral, remove worktrees
4. On conflict or test failure → mail Admiral for manual intervention

The only change is step 4: Ghost should attempt resolution before escalating.

## Goals / Non-Goals

**Goals:**
- Ghost reads each conflicting change's `specs/` and `tasks.md` before resolving.
- Ghost resolves conflicts additively where both changes' intents can coexist.
- Ghost documents every resolution decision in the Admiral mail.
- Ghost escalates only when conflicts are genuinely irreconcilable or tests cannot be made to pass after resolution attempts.

**Non-Goals:**
- Changing how Raven dispatches Ghost (unchanged).
- Changing the success path (unchanged).
- Giving Ghost unlimited retry attempts — one resolution pass, then escalate.

## Decisions

### Decision: One resolution pass, then escalate

Ghost gets one attempt: read specs/tasks, resolve, re-run tests. If tests still fail after that pass, escalate. This avoids an open-ended loop while still catching the common case (non-overlapping changes that git marks as conflicting but are actually compatible).

### Decision: Resolution strategy is additive-first

Instruct Ghost to treat conflicting hunks as additive by default — if both changes touch the same file in non-overlapping ways, accept both. Only choose one side when the changes are genuinely mutually exclusive (e.g. both rename the same function differently). The specs for each change define the intended behaviour; Ghost uses those to decide which side is correct when a true conflict exists.

### Decision: Every decision is logged in the Admiral mail

Whether the merge succeeds after resolution or escalates, the Admiral mail includes a per-conflict summary: what conflicted, what Ghost chose, and why. This keeps the Admiral informed without requiring manual intervention for resolved conflicts.

## Migration Plan

Edit `academy/orders/sdd.md` only. Existing crews using the SDD captain will pick up the new instructions on their next check-in tick, since `sdd.md` is read at order-resolution time, not baked into the cron job at creation.
