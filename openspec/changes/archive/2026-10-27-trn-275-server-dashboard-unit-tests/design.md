## Context

`server.py` reports 0% unit coverage because the file is never imported by
the test suite — not because its logic is hard to test. Investigation shows
the middleware layer (`BearerAuthMiddleware`, `SecurityHeadersMiddleware`,
`TransportSecretMiddleware`) is already covered in `test_auth.py`; the gap is
`server.py`'s own utility functions and the `DashboardGate` class in
`dashboard.py`. The e2e suite covers the route handlers themselves adequately.

The existing unit test pattern (see `test_auth.py`) is ASGI `__call__` invocation
with no live server. `DashboardGate` and `_handle_health` fit that pattern.
The server.py utility functions (`_extract_crew_proxy_parts`,
`_sanitise_query_string`, `_parse_ttl_seconds`, `_jwt_exp`,
`_cookie_near_expiry`) are pure functions and can be unit-tested with no
scaffolding at all.

## Goals / Non-Goals

**Goals:**
- Cover `dashboard.py` pure logic: per-session CSRF, cookie flags,
  open-redirect validation, forged-CSRF rejection.
- Cover `server.py` pure utility functions and the health handler.
- Every test guards a named failure mode.

**Non-goals:**
- Route handler tests for MCP tools (dispatch, launch, nuke, etc.) — these
  are integration paths already covered by e2e.
- Boosting coverage in `lifecycle.py`, `podman.py`, or `tools.py`.

## Decisions

**Use direct ASGI `__call__` invocation, not Starlette TestClient.**
Rationale: consistent with `test_auth.py`'s established pattern. `TestClient`
pulls in more of the route table and makes middleware isolation harder. Direct
invocation keeps each test class scoped to one class.

**Construct `DashboardGate` with injected dependencies.**
`DashboardGate.__init__` already takes `session_ttl_secs`, `api_key`, and
`external_url` as explicit arguments — no patching needed. Tests construct an
instance with known values and call handler methods via `scope`/`send`/`receive`.

**Test `_validate_next_url` as a pure function.**
It lives at module level in `dashboard.py`, takes a string, returns a string.
No ASGI scaffolding required.

**Import `server.py` utility functions directly.**
Functions like `_jwt_exp` and `_cookie_near_expiry` are importable without
starting a server. The dual import shim (`try: import server` /
`except: from transport import server`) already used in other test files handles
the flat vs package layout correctly.

**Per-session CSRF: test via two separate DashboardGate instantiations or via
the gate's session-creation path.**
The per-session CSRF token is issued when a session is created. Two calls to
the login-page handler with no existing session should produce distinct
`gs_csrf` values, testable without a live HTTP client.

## Risks / Trade-offs

**[Risk] server.py import pulls in module-level globals that fail outside container.**
→ Mitigation: import only the specific utility functions needed (`from transport.server import _jwt_exp, ...`). Avoid importing the app object or anything that calls `Config.from_env()` at import time.

**[Risk] DashboardGate handler methods may reference module-level config.**
→ Mitigation: inspect each handler before writing tests; if they reference
`_config` or `_api_key` at module scope rather than via the gate's own
attributes, mock only those at the module level (acceptable one-off).

## Migration Plan

1. Add `tests/unit/test_server.py`.
2. Add `tests/unit/test_dashboard.py`.
3. Run `pytest tests/unit/ -q` — all existing tests must still pass.
4. No production code changes. No deploy step.
