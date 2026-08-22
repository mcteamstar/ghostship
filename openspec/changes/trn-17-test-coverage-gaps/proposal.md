## Why

Three critical paths in `transport/server.py` have zero or inadequate test
coverage, identified in the holistic code review (docs/research/code-review.md).
These paths handle startup reconciliation, background idle-stop monitoring, and
crew setup sequencing — all of which have caused or could cause production
issues silently.

## What Changes

### `_reconcile_registry` (zero tests)

The startup reconciliation loop sweeps orphaned login containers, restarts
stopped crews, and refreshes cookies. It is one of the most complex startup
paths in the transport and has never been tested. Key behaviours to cover:

- Orphaned login container is removed from registry
- Stopped crew is restarted and cookie refreshed
- Running crew with healthy gateway is left alone
- Running crew with dead gateway is restarted (post-TRN-2)
- Partial/stale `launching` placeholder entries are cleaned up

### `_idle_monitor` (zero tests)

The background idle-stop thread runs continuously and stops inactive crews.
No tests exist. Key behaviours to cover:

- Crew with an active cron job is NOT stopped
- Crew with a running dispatch task is NOT stopped
- Crew that is genuinely idle (no cron, no tasks, timeout elapsed) is stopped
  and registry updated
- No false-stop when `last_run_ts` is recent
- Stopped crew is not double-stopped

### `_finish_crew_setup` ordering (inadequate coverage)

The single existing test is heavily mocked and does not verify that setup steps
happen in the correct order. A permutation of: auth inject → config patch →
restart → agent/skill/steering copy → OpenSpec seed → model patch → admiral
secret inject → policy inject → cookie mint could silently break. The test
should assert the sequence, not just the outcome.

### Login flow edge cases (no tests)

The PTY-based login flow (`_handle_login_post`) has a happy-path test only.
Untested paths:
- URL not found within 15 seconds → 500
- Region prompt answered
- `_drain_pty` background thread behaviour
- Concurrent `POST /login` rejection (TOCTOU path)

## Impact

- `transport/test_transport.py` — new test classes for each area above
- No changes to `transport/server.py` (test-only change)
