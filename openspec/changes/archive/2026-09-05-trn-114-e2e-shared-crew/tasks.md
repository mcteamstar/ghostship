## 1. test_transport_e2e.py — module-level shared fixture

- [x] 1.1 Add `SHARED_CREW_ID = "e2e-shared-main"` constant at module level (after imports, before first test class)
- [x] 1.2 Add `setUpModule()`: nuke any stale `SHARED_CREW_ID` crew, launch it, raise `RuntimeError` if `status != "ready"`; guard with `@unittest.skipUnless(GHOSTSHIP_E2E_URL, _SKIP_REASON)` equivalent (skip if `GHOSTSHIP_E2E_URL` unset)
- [x] 1.3 Add `tearDownModule()`: nuke `SHARED_CREW_ID` crew, swallow exceptions

## 2. test_transport_e2e.py — TestDispatchPickup

- [x] 2.1 Remove `setUpClass` and `tearDownClass` entirely
- [x] 2.2 Change `CREW_ID = "e2e-dispatch"` to `CREW_ID = SHARED_CREW_ID`
- [x] 2.3 Verify `test_dispatch_and_pickup` body needs no other changes (still references `self.CREW_ID`)

## 3. test_transport_e2e.py — TestSupplyEvac

- [x] 3.1 Remove `setUpClass` and `tearDownClass` entirely
- [x] 3.2 Change `CREW_ID = "e2e-files"` to `CREW_ID = SHARED_CREW_ID`
- [x] 3.3 Verify `test_supply_and_evac` body needs no other changes

## 4. test_transport_e2e_extended.py — module-level shared fixture

- [x] 4.1 Add `SHARED_CREW_ID = "e2e-shared-ext"` constant at module level
- [x] 4.2 Add `setUpModule()`: nuke any stale `SHARED_CREW_ID` crew, launch it, raise `RuntimeError` if not ready; guard with `GHOSTSHIP_E2E_URL` check
- [x] 4.3 Add `tearDownModule()`: nuke `SHARED_CREW_ID` crew, swallow exceptions

## 5. test_transport_e2e_extended.py — TestErrorPaths

- [x] 5.1 Remove `setUpClass` and `tearDownClass` entirely (the TRN-112 `e2e-err-shared` crew is replaced by the module-level shared crew)
- [x] 5.2 Change `CREW_ID = "e2e-err-shared"` to `CREW_ID = SHARED_CREW_ID`
- [x] 5.3 Verify `test_nuke_nonexistent_crew`, `test_dispatch_nonexistent_crew`, `test_evac_nonexistent_crew` still use `self.GHOST_CREW` and need no crew — no changes
- [x] 5.4 Verify `test_pickup_nonexistent_task` still uses its own `crew_id = "e2e-err-pickup"` launch/nuke block — no changes
- [x] 5.5 Verify `test_launch_duplicate_crew` still uses its own `crew_id = "e2e-err-dup"` launch/nuke block — no changes
- [x] 5.6 Verify `test_nuke_without_confirm` still uses its own `crew_id = "e2e-err-noconfirm"` launch/nuke block — no changes

## 6. test_transport_e2e_extended.py — TestScheduleTool

- [x] 6.1 Remove `setUpClass` and `tearDownClass` entirely
- [x] 6.2 Change `CREW_ID = "e2e-schedule"` to `CREW_ID = SHARED_CREW_ID`
- [x] 6.3 Verify `test_create_list_cancel` and `test_cancel_nonexistent_job` reference `self.CREW_ID` and need no other changes

## 7. test_transport_e2e_extended.py — TestResponseSchemas

- [x] 7.1 Remove `setUpClass` and `tearDownClass` entirely
- [x] 7.2 Change `CREW_ID = "e2e-schema"` to `CREW_ID = SHARED_CREW_ID`
- [x] 7.3 Update `test_launch_response_shape`: it currently reads from `cls._launch_result` stored in `setUpClass` — with `setUpClass` gone, store the module-level launch result in a module variable (e.g. `_SHARED_LAUNCH_RESULT`) in `setUpModule` and read from it in the test; verify `crew_id`, `status`, `container`, `gateway_url` assertions still hold
- [x] 7.4 Verify remaining schema tests (`test_crews_response_shape`, `test_dispatch_response_shape`, `test_pickup_list_shape`, `test_supply_response_shape`) use `self.CREW_ID` and need no other changes

## 8. Verification

- [x] 8.1 Run `python3 -m unittest discover -s tests/e2e -p "test_*.py" -t .` locally (or against academy) and confirm no `setUpClass` launch/teardown appears in output for stateless classes
- [x] 8.2 Confirm total launch count in test output: expect 1 (`setUpModule` main) + 1 (`setUpModule` ext) + 1 (steer) + 1 (lifecycle) + up to 3 (error-path throw-aways) = ≤ 7 launches, with only 2 surviving between class transitions
