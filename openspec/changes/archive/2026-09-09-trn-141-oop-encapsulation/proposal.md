## Why

`server.py` and `auth.py` carry scattered module-level mutable state and oversized functions that make the codebase harder to read, test, and reason about. With `trn-143-server-slimming` complete, this change introduces four targeted OOP encapsulations to address the highest-value cohesion gaps.

## What Changes

- Introduce `DashboardGate` class encapsulating the five dashboard module-level globals (`_dashboard_throttle`, `_gs_sessions`, `_dashboard_csrf_token`, `_dashboard_port_crew`, `_dashboard_port_crew_lock`) and their four HTTP handler methods into a single stateful object; lives in `transport/caddy.py` or a new `transport/dashboard.py`
- Introduce `CaddyPortal` class replacing the post-import mutation pattern (`_caddy.PORT = PORT`, `_caddy.GA_API_KEY = ...`) with a properly constructed instance; methods cover port allocation/release and crew registration/deregistration; passed as a dependency to `launch`, `nuke`, and dashboard handlers in `server.py`
- Introduce `AsyncMiddlewareBase` — a ~15-line base class in `transport/auth.py` eliminating the repeated non-HTTP ASGI scope pass-through pattern across `TransportSecretMiddleware`, `RateLimitMiddleware`, and `BearerAuthMiddleware`; decompose `BearerAuthMiddleware.__call__` (currently ~197 lines, 6-level nesting) into `_dispatch_websocket`, `_dispatch_public_route`, `_dispatch_file`, and `_dispatch_authenticated` sub-methods
- Decompose the `captain()` MCP tool (~385 lines, 7-level nesting) by extracting `_captain_do_order`, `_captain_do_stop`, and `_captain_do_status` helper functions; the tool itself becomes a thin dispatcher

## Capabilities

### New Capabilities

_(none — pure internal refactor, no new externally observable behaviour)_

### Modified Capabilities

_(none — `skip_specs: true` — all changes are implementation-internal; no spec-level behaviour changes)_

## Impact

- `transport/server.py` — dashboard globals removed, `DashboardGate` instance constructed; `_caddy.*` post-import mutations replaced with `CaddyPortal`; `captain()` tool slimmed to dispatcher
- `transport/auth.py` — `AsyncMiddlewareBase` added; all three middleware classes refactored; `BearerAuthMiddleware.__call__` decomposed
- `transport/caddy.py` (or new `transport/dashboard.py`) — `DashboardGate` and `CaddyPortal` classes added
- No public API, MCP tool surface, or configuration changes; all existing tests must pass without modification
