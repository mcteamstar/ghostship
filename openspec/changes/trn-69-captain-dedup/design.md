# TRN-69 Design — Captain Escalation Deduplication

## D1: Extend `_RAVEN_SELF_CANCEL` — report-and-pause

Current text (line ~1191 in `transport/server.py`):
```
Once you're genuinely satisfied the standing orders are met, pause your own check-in job
(named "captain", the only one in this crew) through the CLI, and confirm via `cron list`
that it actually stopped before you hold — don't ask the Admiral to do it for you, and
don't report it done without checking.
```

Replace with:
```
Once you're genuinely satisfied the standing orders are met — including after you have sent
a completion report to the Admiral for a one-shot task — pause your own check-in job (named
"captain", the only one in this crew) through the CLI, and confirm via `cron list` that it
actually stopped before you hold. Do not ask the Admiral to do it for you, and do not report
it done without checking.

For monitoring orders (watch a task, report when done): the standing order is satisfied the
moment you send the completion report. Pause immediately after sending — do not wait for a
further instruction or the next cycle.
```

## D2: Add deduplication check to `_CAPTAIN_CHECKIN_TASK`

Add a paragraph to `_CAPTAIN_CHECKIN_TASK` (after the standing orders reading section, before
the action list) instructing Raven to check for prior reports before sending:

```
Before sending any report to the Admiral about a completed task, check /var/mail/admiral/
(both new/ and cur/) for a prior message whose body references the same task ID. If a prior
report already exists for that task, do not send another one — instead, treat the standing
order as satisfied and pause the cron.
```

## D3: Affected code

Single file: `transport/server.py`

- `_RAVEN_SELF_CANCEL` (~line 1191) — add report-and-pause clause
- `_CAPTAIN_CHECKIN_TASK` (~line 1256) — add deduplication paragraph

No changes to the captain API, captain tool, or any other file.

## D4: Test approach

The captain check-in task is a string template — tests verify:
1. `_RAVEN_SELF_CANCEL` contains the word "report" (regression: ensure new clause present)
2. `_CAPTAIN_CHECKIN_TASK` contains dedup instruction (substring check)

Behavioural verification is integration-level: dispatch a monitoring captain, let the Banshee
complete, and assert admiral mail count stays at 1 after multiple cron cycles. This is
captured as a manual integration step in tasks.md.

## D5: What this does NOT fix

- Race condition where two concurrent check-ins both see a completed task before either
  has paused the cron. The dedup check (D2) mitigates this but doesn't eliminate it
  entirely — Fix 2 is a heuristic, not a lock.
- The broader duplicate-dispatch problem (two Ravens spawned in the same cycle) — that is
  handled by the existing intent-marker protocol in the SDD template, not by this change.
