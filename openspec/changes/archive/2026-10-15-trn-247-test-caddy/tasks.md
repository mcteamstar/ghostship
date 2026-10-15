## 1. Create test file scaffold

- [x] 1.1 Create `tests/unit/test_caddy.py` with standard module docstring,
  imports (`unittest`, `unittest.mock.patch`, `unittest.mock.MagicMock`,
  `unittest.mock.call`), and the dual import shim for `transport.caddy`
  (matching the pattern in `test_config.py` / `test_login.py`)
- [x] 1.2 Import the symbols under test: `CaddyPortal`, `_dashboard_ports_in_use`,
  `_allocate_dashboard_port`, `_release_dashboard_port`, `_caddy_register_crew`,
  `_caddy_deregister_crew`, `_caddy_admin_url` from `transport.caddy`

## 2. TestCaddyPortalPortPool

- [x] 2.1 Add `TestCaddyPortalPortPool(unittest.TestCase)` with `setUp` / `tearDown`
  that clears `_dashboard_ports_in_use` before and after each test (use
  `transport.caddy._dashboard_ports_in_use.clear()`)
- [x] 2.2 `test_allocate_returns_range_start_when_pool_empty` — construct
  `CaddyPortal(port=0, api_key="", port_range_start=8000, port_range_size=10)`,
  call `allocate_port()`, assert result is `8000` and `8000` is in
  `_dashboard_ports_in_use`
- [x] 2.3 `test_allocate_skips_in_use_port` — pre-populate `_dashboard_ports_in_use`
  with `{8000}`, assert `allocate_port()` returns `8001`
- [x] 2.4 `test_allocate_raises_when_pool_exhausted` — pre-populate all 10 ports
  `{8000, …, 8009}`, assert `allocate_port()` raises `RuntimeError`
- [x] 2.5 `test_release_then_reallocate` — allocate a port, release it via
  `release_port(port)`, call `allocate_port()` again, assert the same port
  is returned
- [x] 2.6 `test_release_absent_port_is_noop` — call `release_port(9999)` on an
  empty pool, assert no exception and `_dashboard_ports_in_use` remains empty

## 3. TestModuleLevelPortWrappers

- [x] 3.1 Add `TestModuleLevelPortWrappers(unittest.TestCase)` with `setUp` /
  `tearDown` that clears `_dashboard_ports_in_use` and patches
  `transport.caddy.GA_DASHBOARD_PORT_RANGE_START` / `GA_DASHBOARD_PORT_RANGE_SIZE`
  to a small deterministic range (e.g. start=9100, size=5)
- [x] 3.2 `test_allocate_dashboard_port_returns_range_port` — call
  `_allocate_dashboard_port()`, assert result is within `[9100, 9104]`
- [x] 3.3 `test_release_dashboard_port_removes_port` — allocate then release via
  `_release_dashboard_port(port)`, assert port is no longer in
  `_dashboard_ports_in_use`

## 4. TestCaddyPortalRegisterCrew — config and routing structure

- [x] 4.1 Add `TestCaddyPortalRegisterCrew(unittest.TestCase)` — create a helper
  `_make_portal(api_key="")` that returns a `CaddyPortal(port=5476,
  api_key=api_key, port_range_start=9000, port_range_size=10)` and a
  `_call_register(portal, crew_id="abc", port=8765, status=200)` helper that
  patches `transport.caddy.httpx.put` to return a `MagicMock(status_code=status)`
  and calls `portal.register_crew(crew_id, port)`; returns the mock for
  assertions
- [x] 4.2 `test_put_200_succeeds` — assert no exception raised, mock called once
- [x] 4.3 `test_put_201_succeeds` — same as 4.2 with status 201
- [x] 4.4 `test_put_409_idempotent` — status 409, assert mock called exactly once
  (no retry)
- [x] 4.5 `test_listen_port_in_body` — extract the `json=` kwarg from the mock
  call, assert `body["listen"] == [":8765"]`
- [x] 4.6 `test_server_id_in_body` — assert `body["@id"] == "crew-abc"`
- [x] 4.7 `test_rewrite_uri_uses_crew_prefix` — extract the reverse proxy handler
  from the HTTP catch-all route, assert its `rewrite["uri"]` starts with
  `/crews/abc/ui`
- [x] 4.8 `test_transport_token_header_injected` — assert the reverse proxy
  handler's `headers["request"]["set"]["X-Transport-Token"]` equals
  `["{file./run/secrets/ga-transport-secret}"]`
- [x] 4.9 `test_ws_route_before_http_route` — assert `routes[0]` contains a
  `match` on `Connection: Upgrade` and `routes[1]` does not contain such a
  match (WebSocket route is first)
- [x] 4.10 `test_forward_auth_present_when_api_key_set` — call with
  `api_key="secret"`, extract the HTTP catch-all route `handle` list, assert
  it has at least two handlers and the first one has `rewrite.uri` containing
  `/dashboard/auth`
- [x] 4.11 `test_forward_auth_absent_when_api_key_empty` — call with
  `api_key=""`, assert the HTTP catch-all `handle` list has exactly one handler
  (the reverse proxy, no forward-auth)
- [x] 4.12 `test_put_url_includes_crew_id` — assert the URL passed to
  `httpx.put` equals
  `"http://ga-portal:2019/config/apps/http/servers/crew-abc"`

## 5. TestCaddyPortalRegisterCrew — retry and error paths

- [x] 5.1 `test_retry_on_500_then_success` — patch `transport.caddy.time.sleep`
  to no-op; script `httpx.put` to return 500 then 200 (use
  `side_effect=[Mock(status_code=500), Mock(status_code=200)]`); assert `put`
  called exactly twice and no exception raised
- [x] 5.2 `test_no_exception_after_all_retries_exhausted` — script three 500
  responses; assert no exception raised (only a warning log)
- [x] 5.3 `test_retry_on_connection_error_then_success` — script `httpx.put`
  to raise `Exception("timeout")` on first call then return 200; patch sleep;
  assert no exception and two calls made
- [x] 5.4 `test_no_exception_all_retries_connection_error` — script three
  `Exception` raises; assert no exception raised

## 6. TestCaddyPortalDeregisterCrew

- [x] 6.1 Add `TestCaddyPortalDeregisterCrew(unittest.TestCase)` with a helper
  `_call_deregister(crew_id="abc", status=200)` that patches
  `transport.caddy.httpx.delete` and calls `portal.deregister_crew(crew_id)`;
  returns the mock
- [x] 6.2 `test_delete_url_includes_crew_id` — assert the URL passed to
  `httpx.delete` equals `"http://ga-portal:2019/id/crew-abc"`
- [x] 6.3 `test_delete_200_succeeds` — assert no exception
- [x] 6.4 `test_delete_204_succeeds` — assert no exception
- [x] 6.5 `test_delete_404_graceful` — assert no exception raised (already gone)
- [x] 6.6 `test_delete_500_no_exception` — assert no exception (nuke must not block)
- [x] 6.7 `test_delete_connection_error_no_exception` — script `httpx.delete` to
  raise `Exception("conn refused")`; assert no exception raised

## 7. TestCaddyModuleLevelHelpers

- [x] 7.1 Add `TestCaddyModuleLevelHelpers(unittest.TestCase)`
- [x] 7.2 `test_caddy_admin_url_constant` — assert `_caddy_admin_url()` returns
  `"http://ga-portal:2019"`
- [x] 7.3 `test_portal_constructor_stores_fields` — construct
  `CaddyPortal(port=1234, api_key="k", port_range_start=5000, port_range_size=20)`;
  assert `_port == 1234`, `_api_key == "k"`, `_range_start == 5000`,
  `_range_size == 20`
- [x] 7.4 `test_caddy_register_crew_module_wrapper_issues_put` — patch
  `transport.caddy.httpx.put` to return `MagicMock(status_code=200)` and
  `transport.caddy.GA_API_KEY` to `""` (no forward-auth); call
  `_caddy_register_crew("test", 9000)`;
  assert `put` was called once with a URL containing `crew-test`
- [x] 7.5 `test_caddy_deregister_crew_module_wrapper_issues_delete` — patch
  `transport.caddy.httpx.delete` to return `MagicMock(status_code=200)`; call
  `_caddy_deregister_crew("test")`; assert `delete` was called once with a URL
  containing `crew-test`

## 8. Verification

- [x] 8.1 Run `pytest tests/unit/test_caddy.py -v` and confirm all tests pass
- [x] 8.2 Run `pytest tests/unit/` and confirm no regressions in existing tests
- [x] 8.3 Confirm `_dashboard_ports_in_use` is empty after the full unit suite
  (no cross-test leakage)
