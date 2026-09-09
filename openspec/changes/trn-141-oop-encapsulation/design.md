## Context

See proposal.md for motivation. The key structural issues to address:

- **Dashboard state** (`_dashboard_throttle`, `_gs_sessions`, `_dashboard_csrf_token`, `_dashboard_port_crew`, `_dashboard_port_crew_lock`) lives at module level in `server.py` (~line 776–1042), alongside four HTTP handler functions that operate on it. There is no single object that owns this cluster.
- **`caddy.py` post-import mutation** (`_caddy.PORT = PORT`, `_caddy.GA_API_KEY = ...`, lines 509–512 in `server.py`) is the only way runtime config reaches `caddy.py` today; the module docstring explicitly describes this pattern as intentional to avoid a circular import. The `CaddyPortal` class replaces this.
- **Middleware** (`TransportSecretMiddleware`, `RateLimitMiddleware`, `BearerAuthMiddleware`) each repeat `if scope["type"] != "http": await self.app(...); return` as their first line. `BearerAuthMiddleware.__call__` is ~197 lines with 6-level nesting.
- **`captain()` MCP tool** is ~385 lines with three major code paths (order/stop/status), each embedded inline at 7-level nesting.

`trn-143-server-slimming` is complete. The current state of `server.py` after that change is the baseline.

## Goals / Non-Goals

**Goals:**
- All four encapsulations in scope (DashboardGate, CaddyPortal, AsyncMiddlewareBase, captain decomposition)
- Every existing test passes without modification after the refactor
- No change to public API, MCP tool surface, or configuration interface

**Non-Goals:**
- Moving business logic or changing any observable behaviour
- Introducing new abstractions beyond the four specified
- Resolving the circular-import constraint differently (the `CaddyPortal` design must respect the existing import order)

## Decisions

### 1. DashboardGate — lives in `transport/dashboard.py`

`DashboardGate` needs to import `security.py` (for `Throttle` and `SessionStore`). `caddy.py`'s documented import constraint is stdlib, httpx, config, and registry only — never server or lifecycle — to keep the dependency graph acyclic. Adding a `security` import would violate that constraint and blur caddy.py's single responsibility (Caddy admin API + port pool).

A new `transport/dashboard.py` is the right home: it owns the session/auth state cluster, imports `security`, and keeps `caddy.py` clean. `caddy.py` continues to own only port allocation and Caddy admin API helpers; `CaddyPortal` (decision 2) also lives there since it wraps exactly those concerns.

`DashboardGate.__init__` accepts `session_ttl_secs`, `api_key`, and `tls_mode` from `cfg` — making the previously implicit dependencies explicit. The four handler methods (`handle_login_get`, `handle_login_post`, `handle_logout_post`, `handle_auth`) become instance methods. `_dashboard_port_crew` and its lock move from `server.py` into the instance.

`server.py` constructs one `DashboardGate` instance and passes it to `BearerAuthMiddleware` in place of the four standalone handler references.

**Alternative considered:** Put in `caddy.py`. Rejected — `caddy.py` does not import `security`; adding that import breaks its documented acyclic constraint and conflates portal session management with Caddy admin API concerns.

### 2. CaddyPortal — constructor replaces post-import mutation

`CaddyPortal` wraps the existing module-level functions in `caddy.py` (`_allocate_dashboard_port`, `_release_dashboard_port`, `_caddy_register_crew`, `_caddy_deregister_crew`) as instance methods (`allocate_port`, `release_port`, `register_crew`, `deregister_crew`). The module-level `PORT`, `GA_API_KEY`, etc. globals are replaced by instance attributes set in `__init__`.

`server.py` constructs `CaddyPortal(port=PORT, api_key=GA_API_KEY, ...)` after secrets load — replacing the four `_caddy.X = Y` lines. The instance is passed as a dependency to `launch`, `nuke`, and relevant handlers.

The circular-import constraint (caddy must not import server) is preserved: `CaddyPortal` is defined in `caddy.py` and constructed in `server.py`.

### 3. AsyncMiddlewareBase — minimal base class in `transport/auth.py`

```python
class AsyncMiddlewareBase:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        await self.handle_http(scope, receive, send)

    async def handle_http(self, scope, receive, send) -> None:
        raise NotImplementedError
```

All three middleware classes inherit from `AsyncMiddlewareBase` and implement `handle_http`. `SecurityHeadersMiddleware` (which already has different non-HTTP handling) is exempt — it may stay as-is.

`BearerAuthMiddleware.handle_http` delegates to three private sub-methods (WebSocket handling disappears — `AsyncMiddlewareBase.__call__` already passes non-HTTP scopes through, so `BearerAuthMiddleware` never sees a WebSocket scope in `handle_http`):
- `_dispatch_public_route` — public routes (no auth check)
- `_dispatch_file` — presigned-URL file app pass-through
- `_dispatch_authenticated` — Bearer token validation + downstream dispatch

### 4. captain() decomposition — extract three helper functions

Extract the three action paths from `captain()` into module-level private helpers:

```python
def _captain_do_order(crew_id, message, template, change_name, cron, interval, timezone, fire_immediately, model) -> dict: ...
def _captain_do_stop(crew_id) -> dict: ...
def _captain_do_status(crew_id) -> dict: ...
```

`captain()` itself becomes a ~20-line dispatcher that validates inputs, selects the action, and delegates. The helpers are co-located with `captain()` in `server.py` (no new file needed).

## Risks / Trade-offs

- **DashboardGate handler wiring** — `BearerAuthMiddleware` currently receives handler callables via the `routes`/`public_routes` dicts. Switching to bound methods on `DashboardGate` is a straightforward substitution but requires verifying that all call sites pass the instance's bound methods (not the module-level functions). Risk: low.
- **`_dashboard_port_crew` threading** — this dict is currently protected by `_dashboard_port_crew_lock` in `server.py` and also mutated in `lifecycle.py`. Moving it into `DashboardGate` requires lifecycle.py to access it via the instance. The instance must be importable by lifecycle.py without creating a new cycle. Mitigation: pass the `DashboardGate` instance into the lifecycle functions that need it (same injection pattern as CaddyPortal).
- **Test surface** — tests that directly reference module-level globals (`_gs_sessions`, `_dashboard_csrf_token`, etc.) will need updating to go through the `DashboardGate` instance. This is expected and bounded.

## Migration Plan

- All changes are internal to the transport module; no migration for external callers
- Rollback: revert the affected files; the public API is unchanged
- Sequence: AsyncMiddlewareBase → DashboardGate → CaddyPortal → captain decomposition (lowest to highest blast radius)
