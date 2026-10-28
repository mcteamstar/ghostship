## Why

Several reliability and quality gaps were confirmed in the indy-0.9.1 review
(ID 2da91f40): the launcher waiter timeout (45 s) is shorter than the worst-case
leader restart path (≥120 s), causing spurious 502 errors under memory pressure;
`captain_engine.py` (807 lines) has no direct unit tests; and a handful of small
code quality issues accumulate without enforcement.

## What Changes

- `transport/launcher.py:316` — raise `event.wait(timeout=45)` to `timeout=150`
  (60 + 60 + 30 s headroom for worst-case leader restart).
- `transport/security.py` — call `_sweep()` inside `revoke()` or `validate()` so
  revoked tokens are pruned without waiting for the next `issue()` call; add a
  comment to `RateLimiter` documenting the O(unique_ips × window_secs) memory
  bound.
- `transport/server.py` — remove entry from `_ensure_running_locks` dict on crew
  nuke to prevent unbounded growth.
- Add `tests/unit/test_captain_engine.py` — direct unit tests for
  `captain_engine.py`: `_check_in_memory_pressure` return values,
  `_mail_admiral` no-exception-on-failure, `_captain_do_status` for stopped crew,
  `_captain_do_stop` idempotency.
- CI (`scripts/run.sh` or `.github/workflows/test.yml`) — add `--cov=transport` to
  pytest invocation so coverage gaps surface automatically on every PR.

## Capabilities

### New Capabilities

- `transport/captain-engine-tests`: Direct unit tests for `transport/captain_engine.py`
  covering the eight exported functions. Previously exercised only indirectly via
  mocks in `test_monitors.py`.

### Modified Capabilities

- `crew-lifecycle`: Waiter timeout raised from 45 s to 150 s. Under memory pressure
  the leader restart path can exceed 120 s; waiters previously timed out and raised
  a spurious 502. No state corruption risk — the change only extends how long a
  waiter waits before giving up.

- `transport-test-coverage`: pytest-cov added to CI invocation; coverage gaps now
  surface automatically on every PR run rather than requiring manual inspection.

## Impact

- `transport/launcher.py` — 1-line timeout change
- `transport/security.py` — `_sweep()` call in `revoke()`/`validate()`; RateLimiter
  comment
- `transport/server.py` — `_ensure_running_locks` cleanup on nuke
- `tests/unit/test_captain_engine.py` — new file (~80 lines)
- `scripts/run.sh` or `.github/workflows/test.yml` — add `--cov=transport`
- No breaking changes.
