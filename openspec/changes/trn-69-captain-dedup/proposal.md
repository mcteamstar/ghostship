# TRN-69 — Captain Standing Orders: Suppress Repeated Escalation

## Problem

When Raven monitors a one-shot task (Banshee review, Ghost implementation) and the task
completes, Raven correctly sends a completion summary to admiral mail and holds. But on the
next check-in — 5 minutes later — Raven has no memory of having already reported. It reads
the same completed task, determines the standing order is still active, and sends another
summary. In a 4-hour window this produces 19–24 near-identical admiral mails per crew.

The SDD captain template avoids this because Raven pauses the cron immediately after
confirming the lifecycle is complete (`_RAVEN_SELF_CANCEL`). Free-form monitoring orders
don't have a clear lifecycle-complete signal, so Raven can't know when to pause.

### Root cause

Raven has no durable "already escalated" state. Each check-in starts from scratch. Without a
record that a specific task's result has already been sent to the admiral, every cycle that
sees a completed task looks like a new completion.

## Solution

Two complementary fixes:

### Fix 1: Raven instruction — report-and-pause pattern

Extend `_RAVEN_SELF_CANCEL` (the instruction already injected into every check-in) with an
explicit rule: **once you have sent a completion report to the admiral for a specific task,
pause the captain cron immediately**. The rule applies to any standing order whose work is
a single task or a bounded set of tasks — not an open-ended watch.

The SDD template already does this correctly. The free-form captain prompt needs the same
instruction made explicit: "if you sent a completion report this cycle, pause now."

### Fix 2 (optional, belt-and-suspenders): Sent-mail deduplication check

Before sending a completion report, Raven checks whether a report for the same task ID
already exists in the admiral mailbox (via `/var/mail/admiral/`). If a matching prior mail is
found (same task_id in body), skip the send and pause instead.

This handles the edge case where Fix 1 fails — e.g. the cron fires again before Raven's pause
command takes effect, or two concurrent Raven check-ins both see a completed task.

## Decision

Implement Fix 1 as a change to `_RAVEN_SELF_CANCEL` and `_CAPTAIN_CHECKIN_TASK` in
`transport/server.py`. Fix 2 is implemented as guidance in the Raven check-in prompt — Raven
should scan the admiral mailbox for prior reports before re-sending.

No new transport data structures required. No change to the captain API surface.

## Relationship to TRN-51

TRN-51 (transport-side Maildir access, `captain status` redesign) will eventually let the
transport read sent-mail state directly. TRN-69 is a lower-cost fix at the instruction level
that can ship independently without waiting for TRN-51's infrastructure work.
