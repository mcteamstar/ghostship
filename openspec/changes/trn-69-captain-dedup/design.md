## Context

See proposal.md — Why. Raven check-ins can overlap: a scheduled persistent
check-in and a manually triggered one, or two firings whose execution windows
overlap. Each independently reads `kirocrew spawn list` and OpenSpec/`tasks.md`
state, and a naive "empty spawn list → dispatch" rule lets both spawn the same
persona. The only shared, durable substrate both instances can see is the crew
mailbox (Maildir under `/var/mail/`); `kirocrew spawn list` reflects gateway state
but the `agent` field lags because it is populated asynchronously after
`/api/spawn` returns. The 3-signal protocol already exists in
`academy/orders/sdd.md`; this change makes it a specced behavior contract and
tightens its edges (election, staleness) so it is testable and cannot regress.

## Goals / Non-Goals

**Goals:**
- Guarantee at-most-one dispatch per lifecycle transition under overlapping
  check-ins, using only existing primitives (mailbox, `spawn list`, `/api/spawn`).
- Make the coordination rule precise enough to test: ordered signal evaluation,
  a deterministic election tie-break, and explicit staleness windows.
- Keep the authoritative rule in one place (`sdd.md`) with a cross-reference from
  the standing orders, so the two documents cannot drift.

**Non-Goals:**
- No distributed lock service, database, or new gateway endpoint. The mailbox is
  the coordination medium.
- No change to the SDD lifecycle order (Spectre → Ghost → Banshee → Reaper) or to
  which persona is chosen for a given state — only to how a dispatch is guarded.
- No change to non-SDD, non-persona `spawn run` usage.

## Decisions

**Decision: Mailbox intent marker is the primary signal, not `spawn list`.**
The mailbox write is synchronous and observable by any concurrent check-in the
instant it lands, whereas the `agent` field in `spawn list` appears only after the
gateway processes `/api/spawn`. Making the marker primary closes the window where
both instances see an empty list. Alternative considered: rely on `spawn list`
alone — rejected because the async `agent` field is exactly the race being fixed.

**Decision: Three layered signals, all must be clear.**
Each signal covers a different failure window: the mailbox marker covers the
pre-spawn window, the task-description marker covers an in-flight task whose
mailbox record may be missing or stale, and the agent field is a late confirmation.
Requiring all three to be clear means no single lagging or missing signal can
authorize a duplicate. Alternative considered: a single strongest signal —
rejected because each has a blind spot the others cover.

**Decision: Write-then-elect (post-write election) to break ties.**
Because two instances can both pass the pre-check before either writes, the writer
re-scans after writing and yields to any older pending marker for the same persona.
Ordering is by Maildir arrival / `Date`, tie-broken by `Message-ID`, giving a total
order both instances compute identically. Alternative considered: check-then-write
only — rejected because it has a classic TOCTOU gap; the re-scan after the write is
what makes the election safe.

**Decision: Two-tier staleness keyed on spawn task lifecycle.**
A confirmed intent is stale once its spawn task is done/absent (the work it guarded
is over). A pending intent — one that never reached confirmation, e.g. `/api/spawn`
failed or crashed between write and spawn — is held for one full subsequent
check-in before being declared stale, so a transient failure does not immediately
re-open the race, but a genuinely dead pending marker does eventually clear.
Alternative considered: fixed wall-clock TTL — rejected as fragile across variable
check-in cadence; tying staleness to observable spawn-task state is cadence-agnostic.

## Risks / Trade-offs

- **[Mailbox unavailable / not yet delivered]** → The protocol degrades to the
  `spawn list` signals; document that a missing mailbox is a hold condition, not a
  green light. A dispatching agent that cannot read its mailbox holds rather than
  dispatches.
- **[Stale pending marker briefly blocks a legitimate retry]** → Accepted: one
  extra check-in of delay is far cheaper than a duplicate dispatch. The one-cycle
  hold is bounded.
- **[Clock/arrival skew making election ambiguous]** → Mitigated by the
  `Message-ID` tie-break, which is a deterministic total order independent of clocks.
- **[Documentation drift between sdd.md and STANDING_ORDERS.md]** → Mitigated by
  keeping the full protocol only in `sdd.md` and having the standing-orders section
  reference it rather than restate it.

## Migration Plan

1. Land the protocol text in `academy/orders/sdd.md` and the cross-reference in
   `STANDING_ORDERS.md`. This is prompt/config text, so it takes effect on the next
   check-in that loads the orders — no service restart, no data migration.
2. No rollback data concern: reverting the documents restores prior behavior.
   Because the protocol only adds hold conditions, a partial rollout is safe (it
   can over-hold but never under-guard).
