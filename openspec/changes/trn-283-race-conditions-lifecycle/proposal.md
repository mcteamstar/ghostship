# Proposal

## Why

Three race conditions in the crew lifecycle layer were identified by the indy-0.10.0
independent review. All are low-probability but real: they manifest under concurrent
operations (multiple simultaneous launches, a launch racing a reconcile, or two
callers polling a starting crew) and produce incorrect behaviour rather than clean
errors — stale session cookies causing spurious 401s, silently deleted newly-launched
crews, and double-stop races during container startup.

These bugs are not hypothetical: the transport is an async server handling concurrent
requests, and all three races exist on code paths exercised in normal usage.

## What Changes

### H-1 — `_refresh_cookie` post-lock dict mutation (`lifecycle.py:507–510`)

The crew's in-memory dict entry is mutated with the new cookie value **after** the
registry lock is released. A concurrent request reading `crew["cookie"]` between the
unlock and the mutation sees the old (expired) cookie, sends it to the gateway, gets
a 401, and triggers a redundant second refresh cycle.

**Fix:** Move `crew["cookie"] = new_cookie` inside the lock so it is visible to all
callers atomically with the registry save.

### H-2 — `_reconcile_registry` snapshot-then-delete race (`lifecycle.py:1497–1552`)

`_reconcile_registry` snapshots the crew list under the lock, releases the lock,
computes a `to_remove` set, then re-acquires the lock to write back. Between snapshot
and write-back a concurrent `launch()` can add a new entry for a previously-deleted
`crew_id`. The write-back's `to_remove` pass deletes the new entry without knowing it
was re-registered.

**Fix:** Re-check each `to_remove` cid under the write-back lock: only delete if the
entry's `created_at` timestamp matches the snapshot value (i.e. it was not replaced
by a newer launch).

### H-3 — TOCTOU in `ensure_running` (`launcher.py:265–291`)

`_startup_events` is read without a lock to decide whether to skip the leader
election, then the lock is acquired for the actual election. Two concurrent callers
can both observe `_early_in_progress=False`, both proceed to stop the container, and
both enter the leader election, producing a double-stop and a corrupted startup
sequence.

**Fix:** Consolidate the early-in-progress check and the leader election under a
single lock acquisition so only one caller can win the election.

## Capabilities

### Modified Capabilities

- `crew-lifecycle`: The `_refresh_cookie`, `_reconcile_registry`, and `ensure_running`
  paths gain atomic mutation guarantees under the registry/startup lock.

## Impact

- `transport/lifecycle.py` — H-1 (cookie mutation inside lock), H-2 (timestamp check
  before delete)
- `transport/launcher.py` — H-3 (single-lock election)
- `tests/unit/test_lifecycle.py` / `tests/unit/test_registry_lock.py` — regression
  tests for all three races
