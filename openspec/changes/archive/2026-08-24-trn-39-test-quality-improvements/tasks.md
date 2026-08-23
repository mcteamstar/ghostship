## 1. Portability Header

- [x] 1.1 Add `ScheduleMonitorTests` and `SchedulePersistenceTests` to the
      "Portable (pure unit tests, always run)" list in the portability header
      at the top of `transport/test_transport.py`

## 2. HIGH — Fix Hollow Tests (no TRN-37 dependency)

- [x] 2.1 Rewrite `ScheduleMonitorTests.test_monitor_wakes_crew_and_fires_tick`
      to call the real `_schedule_monitor` function in a thread, patching
      `time.sleep` to raise `StopIteration` on the first call so the loop
      exits after one iteration; assert the spawn POST and registry save were
      made (D1 in design.md)

- [x] 2.2 Rewrite `TestMemoryGate.test_gate_skipped_when_disabled` to call
      `_ensure_crew_running` directly with `GA_MIN_FREE_MEM_GB = 0.0` and
      assert `_wait_for_memory` was never called (D2 in design.md)

- [x] 2.3 Rewrite `ScheduleCancelTests.test_cancel_success` to seed a
      registry entry with `job_id="job-abc"` via `_load_registry`, call
      `schedule(action="cancel", ...)`, and assert the entry is absent from
      the registry captured by the `_save_registry` mock (D3 in design.md)

## 3. HIGH — New Coverage: _advance_next_fire_at and Registry Serialisation
      (requires TRN-37 to pass)

- [x] 3.1 Add `AdvanceNextFireAtTests` class with:
      - `test_interval_branch` — sets `interval_secs=300`, asserts
        `next_fire_at ≈ time.time() + 300`
      - `test_cron_branch` — sets `cron_expr="0 * * * *"` (no interval),
        asserts `next_fire_at > time.time() + 60` (TRN-37 fix, not always +60s);
        annotate `# requires TRN-37`
      - `test_one_shot_branch` — sets `one_shot=True`, asserts
        `next_fire_at == float("inf")`
      (D4 in design.md)

- [x] 3.2 Add `test_registry_rejects_inf_in_next_fire_at` to
      `SchedulePersistenceTests`: build a registry dict with
      `next_fire_at=float("inf")`, assert that
      `json.dumps(reg, allow_nan=False)` raises `ValueError`; annotate
      `# requires TRN-37` (D5 in design.md)

## 4. MEDIUM — Gap Coverage

- [x] 4.1 Add `test_list_falls_back_to_gateway_when_registry_empty` to
      `ScheduleListTests`: patch `_get_crew_schedules` to return `[]`, assert
      the gateway `/api/crons` GET is called and its result is returned
      (D6 in design.md)

- [x] 4.2 Add `test_captain_resume_sets_next_fire_at` to
      `SchedulePersistenceTests`: call `captain(action="order", ...)` on a
      crew where the check-in job already exists but is disabled (resume path),
      capture the registry save, and assert
      `schedule_entry["next_fire_at"] >= time.time() + interval - 1`
      (D7 in design.md)

- [x] 4.3 Add `test_reseed_registers_missing_jobs` to
      `ReconcileRegistryTests`: seed a registry with one schedule whose
      `job_id` is absent from the gateway cron listing, call
      `_reseed_crew_schedules`, and assert the gateway `/api/crons` POST was
      made with the correct `name` and `every` values (D8 in design.md)

- [x] 4.4 Add `test_idle_monitor_cron_401_retries_with_fresh_cookie` to
      `IdleMonitorTests`: patch the cron GET to return 401 on first call,
      patch `_mint_cookie` to return `"new-cookie"`, assert the second cron
      GET is made with `"new-cookie"` in the Cookie header (D9 in design.md)

## 5. Housekeeping

- [x] 5.1 Fix `TestMemoryGate.test_timeout_expires`: change
      `self.assertLess(result, 2.0)` to
      `self.assertAlmostEqual(result, 0.5 * 1024**3 / 1024**3, delta=0.1)`
      (or the appropriate expected value) so the assertion is self-documenting

- [x] 5.2 Replace `LoginGuardClearTests.test_guard_clear_ordering_verified`
      source-inspection with a behavioural test: mock `_nuke_login_container`
      to record a "nuked" flag; after calling `_handle_login_get` up to the
      guard-clear point, assert `_login_pending` is `None` only after the
      nuked flag was set (D10 in design.md)

## 6. Verification

- [x] 6.1 Run `python -m pytest transport/test_transport.py -x -q` (or the
      project's equivalent) and confirm all tests pass (the two TRN-37-
      annotated tests may be skipped or xfail until TRN-37 merges)
