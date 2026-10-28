## 1. Launcher waiter timeout

- [x] 1.1 In `transport/launcher.py`, find `event.wait(timeout=45)` (line ~316)
  and change to `event.wait(timeout=150)`.
- [x] 1.2 Update any related comment that references the 45 s value.
- [x] 1.3 Run `pytest tests/unit/test_launcher.py` (if it exists) to confirm no
  tests rely on the 45 s value. If they do, update the test to use 150.

## 2. SessionStore._sweep on revoke

- [x] 2.1 In `transport/security.py`, add a `self._sweep()` call inside
  `SessionStore.revoke()` after the token is added to `_revoked`.
- [x] 2.2 Add a one-line comment to `RateLimiter` documenting the memory bound:
  `# Memory bound: O(unique_source_ips × window_secs) — lazy per-key eviction, no global sweep.`
- [x] 2.3 Run `pytest tests/unit/test_security.py` (once TRN-278 lands) or confirm
  existing security tests still pass.

## 3. _ensure_running_locks cleanup on nuke

- [x] 3.1 In `transport/server.py`, find the nuke handler / cleanup path and add
  `_ensure_running_locks.pop(crew_id, None)` to remove the stale entry.
- [x] 3.2 Confirm no existing tests break.

## 4. test_captain_engine.py

- [x] 4.1 Create `tests/unit/test_captain_engine.py`. Import functions from
  `transport.captain_engine` (or `captain_engine` in container flat layout).
- [x] 4.2 Add `_check_in_memory_pressure` test: mock host memory below threshold →
  returns non-zero pressure level.
- [x] 4.3 Add `_mail_admiral` failure-safe test: mock mail delivery to raise →
  function does not propagate the exception.
- [x] 4.4 Add `_captain_do_status` stopped-crew test: pass a stopped crew dict →
  returns without raising, includes status field.
- [x] 4.5 Add `_captain_do_stop` idempotency test: call twice → second call does
  not raise.
- [x] 4.6 Run `pytest tests/unit/test_captain_engine.py` — all tests pass.

## 5. pytest-cov in CI

- [x] 5.1 In `scripts/run.sh`, add `--cov=transport --cov-report=term-missing` to
  the `pytest` invocation in the `unit` target.
- [x] 5.2 Confirm `pytest-cov` is listed in test dependencies
  (`requirements-test.txt` or equivalent). Add it if missing.
- [x] 5.3 Run `bash scripts/run.sh --unit` locally — coverage report is printed,
  all tests pass.

## 6. Verification

- [x] 6.1 Run full unit suite: `bash scripts/run.sh --unit` — all tests pass with
  coverage report.
