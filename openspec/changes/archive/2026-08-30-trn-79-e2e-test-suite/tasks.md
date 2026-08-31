## 1. Replace placeholder with real test file

- [x] 1.1 Delete `tests/e2e/test_placeholder.py`
- [x] 1.2 Create `tests/e2e/test_transport_e2e.py` with a module-level skip guard: `GHOSTSHIP_E2E_URL = os.environ.get("GHOSTSHIP_E2E_URL", "")` — all test classes decorated with `@unittest.skipUnless(GHOSTSHIP_E2E_URL, "GHOSTSHIP_E2E_URL not set")`; add a `_mcp_call(url, tool, api_key=None, **kwargs)` helper that POSTs `{"jsonrpc":"2.0","method":"tools/call","params":{"name":tool,"arguments":kwargs},"id":1}` to `POST /mcp` and returns the result

## 2. Health check tests

- [x] 2.1 `TestHealthCheck`: `GET /health` returns 200 with expected JSON shape
- [x] 2.2 `TestHealthCheck`: `GET /version` returns 200 with `{"transport": "<semver>"}` shape

## 3. Crew lifecycle tests

- [x] 3.1 `TestCrewLifecycle.setUp`: nuke any stale `e2e-lifecycle` crew before each test
- [x] 3.2 `TestCrewLifecycle.test_launch_and_nuke`: call `launch` MCP tool, verify crew appears in `crews()` response, call `nuke(confirm=True)`, verify crew is gone

## 4. Dispatch + pickup tests

- [x] 4.1 `TestDispatchPickup.setUp`: launch `e2e-dispatch` crew
- [x] 4.2 `TestDispatchPickup.test_dispatch_and_pickup`: dispatch `echo done` task to ghost, poll `pickup` every 5s up to 120s, verify `done=true` and result is non-empty
- [x] 4.3 `TestDispatchPickup.tearDown`: nuke `e2e-dispatch` crew

## 5. Supply + evac round-trip tests

- [x] 5.1 `TestSupplyEvac.setUp`: launch `e2e-files` crew
- [x] 5.2 `TestSupplyEvac.test_supply_and_evac`: call `supply` to get presigned upload URL, POST a small payload (`hello e2e`), call `evac` to get download URL, fetch it, verify content matches
- [x] 5.3 `TestSupplyEvac.tearDown`: nuke `e2e-files` crew

## 6. Auth gate test

- [x] 6.1 `TestAuthGate`: skip unless both `GHOSTSHIP_E2E_URL` and `GHOSTSHIP_API_KEY` are set
- [x] 6.2 `TestAuthGate.test_unauthenticated_request_rejected`: send a request to `/mcp` without `Authorization` header, verify 401 response

## 7. Verification

- [x] 7.1 Run `GHOSTSHIP_E2E_URL=http://your-academy-host bash tests/run.sh --e2e` — all tests pass against the test host
- [x] 7.2 Run `bash tests/run.sh --e2e` (no env var) — suite skips cleanly with 0 failures
