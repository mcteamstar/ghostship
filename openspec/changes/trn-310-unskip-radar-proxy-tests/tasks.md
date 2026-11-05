# Tasks

## 1. Unskip and rewrite TestRadarApiCrewsSuccess

- [ ] 1.1 Remove the `@unittest.skip(...)` decorator from `TestRadarApiCrewsSuccess` in
  `tests/unit/test_radar_server.py`.
  Add a `_make_fake_httpx(self, response=None, request_error=False)` instance method (copy from
  `TestRadarApiCrewAgents`). Rewrite `test_returns_fleet_payload` to build a `fake_httpx` with
  `response=(200, json.dumps(mock_payload).encode())` and use
  `patch.object(server, "httpx", fake_httpx)` instead of `patch.object(server, "httpx")` with
  the real httpx mocking.
  Verify: `pytest tests/unit/test_radar_server.py::TestRadarApiCrewsSuccess -v` passes (no skip).

## 2. Unskip and rewrite TestRadarApiCrewsTransportDown

- [ ] 2.1 Remove the `@unittest.skip(...)` decorator from `TestRadarApiCrewsTransportDown`.
  Add `_make_fake_httpx` (same copy). Rewrite both test methods:
  - `test_returns_502_on_request_error` → `_make_fake_httpx(request_error=True)`
  - `test_returns_502_on_transport_error_status` → `_make_fake_httpx(response=(500, b"Internal Server Error"))`
  Verify: `pytest tests/unit/test_radar_server.py::TestRadarApiCrewsTransportDown -v` passes (no skip).

## 3. Full suite check

- [ ] 3.1 Run the full radar test class: `pytest tests/unit/test_radar_server.py -v` — all tests
  pass, zero skips.
- [ ] 3.2 Run the full unit suite: `pytest tests/unit/ -q` — no regressions.

## Workflow follow-up

- Assimilate the change after the PR is merged.
