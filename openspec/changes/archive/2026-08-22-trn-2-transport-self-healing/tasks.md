## 1. Gateway Liveness Probe

- [x] 1.1 Add `_probe_gateway(crew_url: str) -> bool` function that performs a GET to the gateway root with a 5-second timeout, returning True on 2xx and False on any error
- [x] 1.2 Integrate the liveness probe into `_ensure_crew_running` — after confirming the container is running, probe the gateway; if the probe fails, proceed with the restart path
- [x] 1.3 Add unit tests for `_probe_gateway` covering success, non-2xx, connection refused, and timeout cases

## 2. Cookie Refresh Recovery

- [x] 2.1 Add `_refresh_cookie(crew: dict, crew_id: str) -> bool` function that re-mints the session cookie via `container_exec`, updates the registry, and returns success/failure
- [x] 2.2 Add unit tests for `_refresh_cookie` covering successful mint, failed mint, and registry update

## 3. Retry Wrapper

- [x] 3.1 Implement `_crew_api_with_recovery(crew, crew_id, method, path, **kw)` that wraps `_crew_api` with the two-phase recovery logic (cookie refresh on 400/401/403, restart on connection error)
- [x] 3.2 Add per-crew locking in `_crew_api_with_recovery` to prevent concurrent recovery races
- [x] 3.3 Ensure the retry cap is exactly one retry per failure class (no infinite loops)
- [x] 3.4 Add unit tests for the full retry flow: stale-cookie path, connection-error path, and double-failure surfacing

## 4. Error Messages

- [x] 4.1 Implement the error message template: "crew <crew_id> is unresponsive — transport attempted <actions> but the gateway did not recover. Suggestion: <next step>."
- [x] 4.2 Verify error messages do not leak tracebacks, raw HTTP bodies, or internal container names
- [x] 4.3 Add unit tests for error message formatting on both recovery-failure paths

## 5. Migrate Call Sites

- [x] 5.1 Replace all tool-handler calls from `_crew_api(...)` to `_crew_api_with_recovery(crew, crew_id, ...)` in `transport/server.py`
- [x] 5.2 Verify internal calls within `_ensure_crew_running` still use raw `_crew_api` (no recursive recovery)
- [x] 5.3 Run existing test suite to confirm no regressions from the call-site migration

## 6. Gateway Health in crews()

- [x] 6.1 Add `gateway_healthy: bool` field to each crew entry in the `crews()` tool output, computed by calling `_probe_gateway` at request time
- [x] 6.2 Return `gateway_healthy: false` for stopped containers without probing
- [x] 6.3 Add unit tests for `crews()` output with healthy, unhealthy, and stopped crew scenarios

## 7. Integration Verification

- [x] 7.1 Add an integration test simulating a gateway crash mid-request and verifying transparent recovery
- [x] 7.2 Add an integration test simulating a stale cookie (400 response) and verifying silent refresh+retry
- [x] 7.3 Add an integration test verifying that double-failure surfaces the actionable error message
