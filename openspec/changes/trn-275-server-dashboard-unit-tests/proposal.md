## Why

`transport/server.py` (554 lines) and `transport/dashboard.py` (117 lines) have
zero unit test coverage. These files contain the HTTP middleware stack, request
routing, and the dashboard CSRF/session/cookie logic — including fixes shipped
in TRN-272 that are entirely untested at the unit level.

## What Changes

- Add `tests/unit/test_server.py` — contract tests for the HTTP middleware stack
  (auth, rate-limiting, security headers) and the health endpoint.
- Add `tests/unit/test_dashboard.py` — unit tests for `DashboardGate`: per-session
  CSRF token uniqueness, cookie flags (SameSite, Secure), open-redirect validation,
  and forged-CSRF rejection.
- Tests use the existing `FakePodmanClient` / dependency-injection patterns from
  `tests/fakes.py`. No `unittest.mock.patch` on module-level globals.
- Every test guards a named failure mode, not just a line of code.

## Capabilities

### New Capabilities

_(None — all changes are test additions; no new externally observable behavior.)_

### Modified Capabilities

- `transport-test-coverage`: Add requirements for server.py middleware and routing
  contract tests.
- `dashboard-session-auth`: Add requirements for per-session CSRF, cookie flags,
  and open-redirect unit tests.

## Impact

- Files changed: `tests/unit/test_server.py` (new), `tests/unit/test_dashboard.py`
  (new).
- No production code changes, no API changes, no breaking changes.
- Unit test count increases; CI pass time increases slightly.
