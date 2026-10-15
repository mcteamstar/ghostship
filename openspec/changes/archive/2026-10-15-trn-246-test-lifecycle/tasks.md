## 1. Test file scaffolding

- [x] 1.1 Create `tests/unit/test_lifecycle.py` with module docstring, imports (`unittest`, `threading`, `unittest.mock.patch`, `FakePodmanClient`), and the seven test class stubs (`TestCleanupCrew`, `TestEnsureRunning`, `TestEnsureRunningConcurrency`, `TestActiveLimit`, `TestMemoryGate`, `TestStateTransitions`, `TestSecretIdentifier`)
- [x] 1.2 Verify `pytest tests/unit/test_lifecycle.py --collect-only` lists all classes and methods without import errors

## 2. TestSecretIdentifier — pure-function tests

- [x] 2.1 Add `test_returns_sha256_prefix` — assert result starts with `"sha256:"` and suffix is exactly 16 hex chars
- [x] 2.2 Add `test_different_inputs_differ` — two distinct strings produce unequal labels
- [x] 2.3 Add `test_deterministic` — same string called twice returns the same label
- [x] 2.4 Run `pytest tests/unit/test_lifecycle.py::TestSecretIdentifier` and confirm all pass

## 3. TestCleanupCrew — teardown and fault isolation

- [x] 3.1 Add `setUp` that creates a `FakePodmanClient` pre-populated with a crew container (`gs-abc`), workspace volume (`gs-vol-abc`), home volume (`gs-home-abc`), and a Podman secret (`admiral-pubkey-abc`)
- [x] 3.2 Add `test_full_cleanup_removes_all_resources` — call `_cleanup_crew(podman, "gs-abc", "gs-vol-abc", "gs-home-abc")` and assert `container_stop`, `container_remove`, `volume_remove` (×2), `secret_remove` all appear in `podman.calls`
- [x] 3.3 Add `test_container_stop_failure_does_not_abort_volume_removal` — monkey-patch `podman.container_stop` to raise `RuntimeError`, call `_cleanup_crew`, assert both `volume_remove` calls still recorded
- [x] 3.4 Add `test_volume_remove_failure_does_not_abort_secret_removal` — monkey-patch `podman.volume_remove` to raise `RuntimeError`, call `_cleanup_crew`, assert `secret_remove` is still called
- [x] 3.5 Add `test_non_crew_container_skips_secret_removal` — call `_cleanup_crew` with a container name not starting with `CREW_CONTAINER_PREFIX`, assert no `secret_remove` call recorded
- [x] 3.6 Run `pytest tests/unit/test_lifecycle.py::TestCleanupCrew` and confirm all pass

## 4. TestEnsureRunning — happy path and nuked-during-restart

- [x] 4.1 Add `setUp` that instantiates `CrewLauncher` with `FakePodmanClient` (container stopped), a seeded registry entry `{status: "stopped", container: "gs-test", ...}`, and patches `lifecycle._wait_gateway` to return `True` and `lifecycle._mint_cookie` to return `"test-cookie"`
- [x] 4.2 Add `test_stopped_crew_starts_and_returns_running_dict` — call `ensure_running(crew, "test")` and assert `container_start` was called, returned dict contains `cookie == "test-cookie"`, registry entry `status == "running"`
- [x] 4.3 Add `test_running_crew_with_live_gateway_returns_immediately` — pre-populate container as running and patch `_probe_gateway` to return `True`; assert `container_start` NOT called
- [x] 4.4 Add `test_nuked_during_restart_returns_sentinel` — remove the registry entry after `container_start` is called (via a side-effect patch); assert result `is _NUKED_DURING_RESTART`
- [x] 4.5 Run `pytest tests/unit/test_lifecycle.py::TestEnsureRunning` and confirm all pass

## 5. TestEnsureRunningConcurrency — leader/waiter, generation, exception propagation

- [x] 5.1 Add `test_concurrent_callers_start_container_once` — launch two threads calling `ensure_running` on the same stopped crew simultaneously; assert `container_start` called exactly once and both threads get a result with `status == "running"`
- [x] 5.2 Add `test_leader_exception_propagates_to_waiters` — patch `container_start` to raise `RuntimeError("start failed")`; launch two threads; assert both receive `RuntimeError` (or subclass) with matching message
- [x] 5.3 Add `test_generation_change_raises_in_waiter` — simulate a third restart cycle starting by incrementing `_launcher._startup_generation["test"]` inside a thread hook before the waiter wakes; assert the waiter raises `RuntimeError` mentioning generation
- [x] 5.4 Run `pytest tests/unit/test_lifecycle.py::TestEnsureRunningConcurrency` and confirm all pass (use `timeout=10` in `join()` so tests do not hang on failure)

## 6. TestActiveLimit — active-crew gate

- [x] 6.1 Add `test_limit_exceeded_raises` — set `GA_MAX_ACTIVE_CREWS=1` via `patch`, add one already-running container to `FakePodmanClient`, call `_check_active_limit`; assert `RuntimeError` raised with limit mentioned
- [x] 6.2 Add `test_limit_not_exceeded_does_not_raise` — `GA_MAX_ACTIVE_CREWS=2`, one running container; assert no exception
- [x] 6.3 Add `test_limit_disabled_zero_never_raises` — `GA_MAX_ACTIVE_CREWS=0`; assert no exception regardless of running containers
- [x] 6.4 Add `test_stale_running_entry_corrected_to_stopped` — registry has `status="running"` for a container that `FakePodmanClient.container_is_running` returns `False` for; call `_check_active_limit` (`GA_MAX_ACTIVE_CREWS=1`); assert no exception raised (stale entry not counted) and registry entry updated to `"stopped"`
- [x] 6.5 Run `pytest tests/unit/test_lifecycle.py::TestActiveLimit` and confirm all pass

## 7. TestMemoryGate — memory gate

- [x] 7.1 Add `test_insufficient_memory_raises` — `GA_MIN_FREE_MEM_GB=4.0`, patch `lifecycle._wait_for_memory` to return `2.0`; call `_check_memory_gate`; assert `RuntimeError` raised mentioning the memory requirement
- [x] 7.2 Add `test_sufficient_memory_does_not_raise` — `GA_MIN_FREE_MEM_GB=4.0`, patch `lifecycle._wait_for_memory` to return `8.0`; assert no exception
- [x] 7.3 Add `test_gate_disabled_zero_never_raises` — `GA_MIN_FREE_MEM_GB=0`; assert no exception even if `_wait_for_memory` would return 0
- [x] 7.4 Run `pytest tests/unit/test_lifecycle.py::TestMemoryGate` and confirm all pass

## 8. TestStateTransitions — end-to-end state graph

- [x] 8.1 Add `test_launching_to_running` — seed registry with `status="launching"`, call a minimal stubbed `_finish_crew_setup` path; assert final status is `"running"` with a cookie set
- [x] 8.2 Add `test_running_to_stopped_via_cleanup` — call `_cleanup_crew` on a running container; assert container absent from `FakePodmanClient` (simulates stop + remove)
- [x] 8.3 Add `test_stopped_to_running_via_ensure_running` — registry `status="stopped"`, call `ensure_running`; assert status becomes `"running"`
- [x] 8.4 Add `test_running_to_removed_via_nuke_path` — call `_cleanup_crew` with all three resources present; assert container, workspace volume, and home volume all absent from `FakePodmanClient`
- [x] 8.5 Run `pytest tests/unit/test_lifecycle.py::TestStateTransitions` and confirm all pass

## 9. Full suite verification

- [x] 9.1 Run `pytest tests/unit/` and confirm the full unit suite passes with no regressions
- [x] 9.2 Confirm no new warnings or `DeprecationWarning` entries introduced by the new file
