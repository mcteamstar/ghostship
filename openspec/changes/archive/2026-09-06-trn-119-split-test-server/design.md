## Context

TRN-116 extracted `transport/auth.py`, `transport/caddy.py`, and `transport/monitors.py` from `server.py` and updated all mock paths in the tests to point at the new module locations. The test classes themselves were not reorganised — they remain in the monolithic `test_server.py` (6217 lines). This change moves them.

`tests/unit/test_trn92_caddy.py` (494 lines) already covers Caddy — it will be absorbed into the new `test_caddy.py` and deleted.

## Goals / Non-Goals

**Goals:**
- Split `test_server.py` into four focused files matching the new module structure
- Absorb `test_trn92_caddy.py` into `test_caddy.py` and remove the old file
- All 698+ tests pass after the split with no mock path changes

**Non-Goals:**
- No new tests
- No mock path changes (already done by TRN-116)
- No changes to test logic or assertions
- No changes to transport code

## Decisions

**Class-to-file mapping:**

`test_auth.py`:
- `BearerAuthMiddlewareTests` — tests `BearerAuthMiddleware` from `transport.auth`
- `TestTrn38SecurityHardening` — middleware security tests
- `TestProxyQuerySanitisation` — query sanitisation (SecurityHeadersMiddleware)
- `StartupWiringTests` (if auth-related wiring)
- Rate limiting tests from `test_trn52_rate_limiting.py` already exist separately — leave them; `test_auth.py` covers middleware only

`test_caddy.py`:
- All content from `test_trn92_caddy.py` (Caddy integration tests)
- `UiPortAllocationTests`, `UiPortLaunchTests`, `UiPortNukeTests`, `CrewsListUiUrlTests`
- `TRN101LaunchPortalTests`, `LaunchDashboardParamTests`, `DashboardRestEndpointTests`
- `CorsOriginInjectionTests`

`test_monitors.py`:
- `IdleMonitorTests`, `IdleMonitorActivityTests`
- `ScheduleMonitorTests`, `ScheduleCancelTests`, `ScheduleCreateValidationTests`, `ScheduleListTests`
- `SchedulePersistenceTests`, `ReseedCronReconcileTests`, `NukeScheduleTests`
- `FireImmediatelyTests`, `DispatchFireAfterTests`
- Supporting fixtures: `IdleMonitorPodman`, `MockHTTPResponse`

`test_server.py` (residual):
- Everything else: `PersonaValidationTests`, `ModelOverrideTests`, `TaskOrchestrationTests`, `PickupTimeoutTests`, `ResourceJobsTests`, `GatewayTokenAndProjectionTests`, `ProxyHandlerTests`, `InstallEnvVarSyncTests`, `GitIdentityInjectionTests`, `Trn89TaskTimestampTests`, `Trn89CrewTimestampTests`, `PickupAgentSubjectsTests`, `FinishCrewSetupOrderingTests`, `LoginGuardClearTests`, `ReadAuthFromCrewTests`, `TestPolicyInjection`, `TestPatchCrewConfig`
- Supporting fixtures: `SetupPodman`, `CookieHeaders`, `CookieResponse`, `CookieHTTP`, `_FakeDownstream`, `_FakeStreamRequest`, `_FakeUpstreamResponse`

**Shared imports:** Each new file copies the relevant imports from `test_server.py`'s import block. Common fixtures used across files (`SetupPodman`, `_FakeDownstream`) stay in `test_server.py` and are imported by the other files if needed — check at move time.

## Risks / Trade-offs

- `tests/run.sh` uses a glob to discover test files — verify new files are picked up automatically before removing the old content
- Some fixtures are shared between test classes (e.g. `_FakeDownstream` is used by both `BearerAuthMiddlewareTests` and `ProxyHandlerTests`) — must check and either duplicate or import across files
