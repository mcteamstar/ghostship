## 1. Fix H-1 — _refresh_cookie atomic cookie update

- [ ] 1.1 In `transport/lifecycle.py`, locate `_refresh_cookie()` and move the
  `crew["cookie"] = new_cookie` assignment inside the `with registry:` block,
  immediately before or after the `registry.save_crew()` call.
- [ ] 1.2 Add a unit test to `tests/unit/test_lifecycle.py`: verify that after
  `_refresh_cookie` completes, the crew dict's `cookie` field matches what was
  persisted to the registry (i.e. no observable stale-cookie window).

## 2. Fix H-2 — _reconcile_registry timestamp guard

- [ ] 2.1 In `transport/lifecycle.py`, `_reconcile_registry()`, capture
  `{cid: entry.get("created_at")}` for all entries in `to_remove` during the
  snapshot pass.
- [ ] 2.2 In the write-back pass (under the write-back lock), before deleting each
  `cid`, re-read the live registry entry and skip deletion if its `created_at`
  differs from the snapshot value.
- [ ] 2.3 Add a unit test: register crew X, snapshot it for removal, re-register X
  with a new `created_at` (simulating a concurrent launch), run write-back, assert X
  is still present.
- [ ] 2.4 Add a unit test for the normal path: register crew X, snapshot for removal,
  no concurrent re-registration, run write-back, assert X is gone.

## 3. Fix H-3 — ensure_running single-lock election

- [ ] 3.1 In `transport/launcher.py`, `ensure_running()` / `_ensure_running_inner()`,
  remove the lock-free `_early_in_progress` / `_startup_events` read that precedes
  the locked election.
- [ ] 3.2 Consolidate the early check and the leader election under a single
  `with self._lock:` acquisition as described in D3.
- [ ] 3.3 Add a unit test using two threads both entering `ensure_running` for the
  same crew simultaneously; assert the container is started exactly once (use a
  counter on FakePodmanClient's `container_start` call).

## 4. Verification

- [ ] 4.1 Run `pytest tests/unit/` — all tests pass.
- [ ] 4.2 Run `bash scripts/run.sh --unit` — full suite green.
