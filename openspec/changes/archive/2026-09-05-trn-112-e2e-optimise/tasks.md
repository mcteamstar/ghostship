## 1. Dependencies

- [x] 1.1 Add `unittest-parallel==1.8.6` to `transport/requirements.txt` as a new line after the existing entries

## 2. test_transport_e2e.py — TestDispatchPickup

- [x] 2.1 Rename `setUp` → `setUpClass` (add `@classmethod`, change `self` → `cls`); replace `self.assertEqual(result.get("status"), "ready")` with `if result.get("status") != "ready": raise RuntimeError(f"Failed to launch {cls.CREW_ID}: {result}")`
- [x] 2.2 Rename `tearDown` → `tearDownClass` (add `@classmethod`, change `self` → `cls`)
- [x] 2.3 Update `test_dispatch_and_pickup` to use `self.__class__.CREW_ID` (or the class attribute directly) — no behavioural change, just reference path update

## 3. test_transport_e2e.py — TestSupplyEvac

- [x] 3.1 Rename `setUp` → `setUpClass` (add `@classmethod`, change `self` → `cls`); replace the status assertion with a `RuntimeError` raise on non-ready (matching step 2.1 pattern)
- [x] 3.2 Rename `tearDown` → `tearDownClass` (add `@classmethod`, change `self` → `cls`)
- [x] 3.3 Update `test_supply_and_evac` to reference class-level `CREW_ID` and `TEST_PATH` correctly — no behavioural change

## 4. test_transport_e2e_extended.py — TestErrorPaths

- [x] 4.1 Add `CREW_ID = "e2e-err-shared"` class attribute (the shared live crew for stateless error-path tests)
- [x] 4.2 Add `setUpClass`: nuke any stale `"e2e-err-shared"` crew, then launch it; raise `RuntimeError` on non-ready
- [x] 4.3 Add `tearDownClass`: nuke `"e2e-err-shared"`
- [x] 4.4 Remove the existing `GHOST_CREW = "e2e-does-not-exist"` class attribute (or retain as a constant for the three non-existent-crew tests that still use it — `test_nuke_nonexistent_crew`, `test_dispatch_nonexistent_crew`, `test_evac_nonexistent_crew`); confirm those three tests need no crew and remain unchanged
- [x] 4.5 Update `test_pickup_nonexistent_task`: keep its own `crew_id = "e2e-err-pickup"` launch/nuke block, unchanged in logic; ensure it does NOT use the shared class crew
- [x] 4.6 Update `test_launch_duplicate_crew`: keep its own `crew_id = "e2e-err-dup"` launch/nuke block, unchanged in logic
- [x] 4.7 Update `test_nuke_without_confirm`: keep its own `crew_id = "e2e-err-noconfirm"` launch/nuke block, unchanged in logic

## 5. test_transport_e2e_extended.py — TestScheduleTool

- [x] 5.1 Rename `setUp` → `setUpClass` (add `@classmethod`, change `self` → `cls`); replace status assertion with `RuntimeError` raise
- [x] 5.2 Rename `tearDown` → `tearDownClass` (add `@classmethod`, change `self` → `cls`)
- [x] 5.3 Update `test_create_list_cancel` and `test_cancel_nonexistent_job` to reference the class-level `CREW_ID` — no behavioural change

## 6. test_transport_e2e_extended.py — TestSteerTool

- [x] 6.1 Rename `setUp` → `setUpClass` (add `@classmethod`, change `self` → `cls`); replace status assertion with `RuntimeError` raise
- [x] 6.2 Rename `tearDown` → `tearDownClass` (add `@classmethod`, change `self` → `cls`)
- [x] 6.3 In `test_steer_running_task_returns_ok`, change the dispatched task string from `"Wait 60 seconds before doing anything, then say DONE."` to `"Wait 25 seconds before doing anything, then say DONE."`
- [x] 6.4 Update both steer tests to reference the class-level `CREW_ID` — no behavioural change

## 7. test_transport_e2e_extended.py — TestResponseSchemas

- [x] 7.1 In `setUpClass`, capture the launch result: change `result = _mcp_call("launch", crew_id=cls.CREW_ID)` to also store it as `cls._launch_result = result` (or rename the local var to make the assignment explicit)
- [x] 7.2 In `test_launch_response_shape`: remove the second `_mcp_call("launch", crew_id="e2e-schema-shape")` block entirely; replace the assertions to operate on `self.__class__._launch_result` (checking `crew_id == cls.CREW_ID`, `status == "ready"`, `"container" in result`, `"gateway_url" in result`)
- [x] 7.3 Remove any remaining references to `"e2e-schema-shape"` crew (launch and cleanup) from `test_launch_response_shape`

## 8. tests/run.sh — parallel runner integration

- [x] 8.1 In the `e2e` case branch of the `for category` loop, add a detection block: `if python3 -c "import unittest_parallel" 2>/dev/null; then USE_PARALLEL=1; else USE_PARALLEL=0; fi`
- [x] 8.2 When `USE_PARALLEL=1`, invoke `run_category e2e python3 -m unittest_parallel -s tests/e2e -p "test_*.py" -t .`
- [x] 8.3 When `USE_PARALLEL=0`, keep the existing serial invocation: `run_category e2e python3 -m unittest discover -s tests/e2e -p "test_*.py" -t .`
- [x] 8.4 Verify the venv bootstrap block (the `uv`/`venv+pip` section near the top of `run.sh`) still installs from `transport/requirements.txt` — no change needed, but confirm the path is correct so `unittest-parallel` is picked up automatically when the venv is (re)created
