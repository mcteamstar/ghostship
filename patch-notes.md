# Patch Notes — release/0.3.0 code quality fixes

## C-1: Move `_caddy_register_crew` outside `_registry_lock` in async handlers

**Files:** `transport/server.py`

`_caddy_register_crew` performs up to 7 s of blocking HTTP I/O with retry
back-off. Calling it while holding `_registry_lock` blocked all other registry
writers (and readers that acquire the lock) for the full retry window.

Fixed in three call sites:

- `_handle_crew_dashboard_post`: extract the cookie value under the lock, save
  the registry, release the lock, then call `_caddy_register_crew`.
- `_handle_crew_dashboard_delete`: update the registry and release the lock,
  then call `_caddy_deregister_crew`.
- `launch()`: extract the cookie value under the lock, save the registry,
  release the lock, then call `_caddy_register_crew`.

## C-2: Fix WS proxy to accept client AFTER upstream connection succeeds

**File:** `transport/server.py` — `_handle_crew_ui_ws_proxy`

`ws.accept()` was called before the upstream `_aconnect_ws` context was
established. If the upstream handshake failed, the client was left with an
accepted but non-functional WebSocket.

Fixed by moving `ws.accept()` inside the `async with _aconnect_ws(...)` block
so it only runs after the upstream connection is confirmed. Added a `except
Exception` handler that sends a close frame with code 1011 (internal error)
when upstream fails before the client is accepted.

## C-4: Wrap `_ensure_crew_running` in `asyncio.to_thread` in proxy handlers

**File:** `transport/server.py`

`_ensure_crew_running` is a synchronous, potentially long-running function
(container start, gateway wait, cookie mint — up to ~30 s). Calling it directly
from `async def` handlers blocks the event loop thread.

Wrapped with `await asyncio.to_thread(...)` in three handlers:
- `_handle_crew_ui_proxy`
- `_handle_crew_ui_ws_proxy`
- `_handle_crew_api_proxy`

## H-2: Fix race condition in `_handle_crew_dashboard_post` double-lock

**File:** `transport/server.py`

The original code read `dashboard_port` from the pre-lock `crew` dict (stale),
then acquired `_registry_lock` for allocation. A concurrent POST could pass the
no-op check simultaneously, resulting in two ports allocated for the same crew.

Fixed by consolidating the no-op check and port allocation into a single
`_registry_lock` section that reads the registry under the lock. The cookie
value is also extracted under the same lock, so the second lock acquisition
(for Caddy registration) is eliminated entirely (Caddy call now runs outside
the lock — see C-1).

## H-4: Mock `_caddy_register_crew` in dashboard POST unit tests

**File:** `tests/unit/test_server.py` — `DashboardRestEndpointTests`

Added `patch.object(server, "_caddy_register_crew")` to every test that
exercises `_handle_crew_dashboard_post`. Without this mock, the test called the
real function which attempted an HTTP request to an unconfigured Caddy admin
URL. Tests now also assert the mock was called with the correct arguments
(`crew_id`, `port`, `crew_cookie`). Added `_load_registry` patches where needed
for the new single-lock code path.

## H-6: Fix `_schedule_monitor` silent tick drop — upgrade log level

**File:** `transport/lifecycle.py`

When a scheduled job tick failed to fire, the failure was logged at `WARNING`
level with no indication that the tick was skipped. Upgraded to `ERROR` and
added "tick dropped" to the message so operators can identify silent job
omissions in log aggregators that filter below ERROR.
