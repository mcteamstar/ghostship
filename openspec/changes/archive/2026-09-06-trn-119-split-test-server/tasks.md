## 1. Prepare shared fixtures

- [x] 1.1 Identify which fixtures in `test_server.py` are used by multiple test classes that will end up in different files (`SetupPodman`, `_FakeDownstream`, `_FakeStreamRequest`, `_FakeUpstreamResponse`, `CookieHeaders`, `CookieResponse`, `CookieHTTP`, `IdleMonitorPodman`, `MockHTTPResponse`) — note which classes use each fixture
- [x] 1.2 For fixtures used by classes moving to another file, either: keep the fixture in `test_server.py` and import it, or duplicate it into the target file — prefer duplication for small fixtures, import for large ones

## 2. Create `tests/unit/test_auth.py`

- [x] 2.1 Create `tests/unit/test_auth.py` with the relevant import block (copy from `test_server.py`, prune to only what auth tests need)
- [x] 2.2 Move `BearerAuthMiddlewareTests`, `TestTrn38SecurityHardening`, `TestProxyQuerySanitisation` into the new file; include any fixtures they depend on
- [x] 2.3 Remove those classes from `test_server.py`
- [x] 2.4 Run `bash tests/run.sh --unit 2>&1 | tail -5` and confirm all tests pass

## 3. Create `tests/unit/test_caddy.py`

- [x] 3.1 Create `tests/unit/test_caddy.py` with the relevant import block
- [x] 3.2 Copy all content from `tests/unit/test_trn92_caddy.py` into the new file
- [x] 3.3 Move `UiPortAllocationTests`, `UiPortLaunchTests`, `UiPortNukeTests`, `CrewsListUiUrlTests`, `TRN101LaunchPortalTests`, `LaunchDashboardParamTests`, `DashboardRestEndpointTests`, `CorsOriginInjectionTests` from `test_server.py` into the new file
- [x] 3.4 Remove those classes from `test_server.py`
- [x] 3.5 Delete `tests/unit/test_trn92_caddy.py`
- [x] 3.6 Run `bash tests/run.sh --unit 2>&1 | tail -5` and confirm all tests pass

## 4. Create `tests/unit/test_monitors.py`

- [x] 4.1 Create `tests/unit/test_monitors.py` with the relevant import block
- [x] 4.2 Move `IdleMonitorTests`, `IdleMonitorActivityTests`, `ScheduleMonitorTests`, `ScheduleCancelTests`, `ScheduleCreateValidationTests`, `ScheduleListTests`, `SchedulePersistenceTests`, `ReseedCronReconcileTests`, `NukeScheduleTests`, `FireImmediatelyTests`, `DispatchFireAfterTests` from `test_server.py` into the new file; include `IdleMonitorPodman` and `MockHTTPResponse` fixtures
- [x] 4.3 Remove those classes from `test_server.py`
- [x] 4.4 Run `bash tests/run.sh --unit 2>&1 | tail -5` and confirm all tests pass

## 5. Verify and clean up

- [x] 5.1 Run the full unit suite: `bash tests/run.sh --unit 2>&1 | tail -5` — confirm all 698+ tests pass
- [x] 5.2 Confirm `test_server.py` contains only the residual classes listed in design.md and no empty import lines
- [x] 5.3 Confirm `tests/run.sh` picks up all four test files (check runner discovery pattern)
- [x] 5.4 Run `openspec status --change trn-119-split-test-server` and confirm planning is complete
