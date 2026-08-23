## Context

`transport/server.py` is a Starlette/ASGI app with a custom `BearerAuthMiddleware` that owns all HTTP routing. Routes outside MCP (file transfer, login/logout, health, version) are either registered in `BearerAuthMiddleware._routes` (a fixed `(method, path) → handler` dict) or detected by path prefix (`/files/` passes to `_file_starlette`). The existing `httpx.Client` (`_http`) is synchronous and used across all crew API calls. The `_ensure_crew_running` / `_require_crew` helpers already handle auto-wake and crew lookup with full recovery logic. See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**
- Add `/crews/{crew_id}/ui[/{path}]` routes that stream a reverse proxy to `http://gs-{crew_id}:5476/`.
- Add `/crews/{crew_id}/api/{path}` routes that do the same with internal session-cookie injection.
- Sit both behind `BearerAuthMiddleware` (auth-required when `GA_API_KEY` set).
- Auto-wake the crew before proxying using `_ensure_crew_running`.
- Stream response bodies without buffering.

**Non-Goals:**
- WebSocket proxying (the crew UI does not use WebSockets through this path).
- Per-crew access control beyond the existing transport-level API key.
- Caching or request transformation beyond cookie injection.

## Decisions

### D1: Async httpx client for proxy handlers

The existing `_http` is a synchronous `httpx.Client` used from synchronous MCP tool functions that run in Starlette's threadpool executor. The new proxy handlers are declared `async def` (Starlette route handlers), so blocking the event loop with `_http` is not acceptable for potentially large response bodies.

**Decision**: introduce a module-level `httpx.AsyncClient` instance (`_async_http`) used exclusively by the proxy handlers. It reuses the same default timeout (60 s) as `_http`.

**Alternative considered**: use `asyncio.get_event_loop().run_in_executor` to call `_http` from the async handler. Rejected — adds thread-pool overhead and complicates streaming; `httpx.AsyncClient` is the direct solution.

### D2: BearerAuthMiddleware path-prefix dispatch

The middleware's current routing uses a fixed `(method, path)` dict that cannot match parameterised paths. The `/files/` prefix bypass (line ~386) is the only existing precedent for prefix-based dispatch.

**Decision**: add two prefix checks inside `BearerAuthMiddleware.__call__` — for `/crews/` paths ending in `/ui` or containing `/ui/`, and for paths containing `/api/` after the crew segment — dispatching to two new async functions `_handle_crew_ui_proxy` and `_handle_crew_api_proxy`. The check happens after auth passes (not in the public-routes block) so `GA_API_KEY` enforcement applies.

Path extraction is done with a simple split on the known prefix pattern: `parts = path.split("/")` then `crew_id = parts[2]`, `sub = "/".join(parts[4:])` — no regex needed given the fixed structure.

**Alternative considered**: mount a Starlette sub-application under `/crews/` with its own `Route` objects. Rejected — wrapping `mcp_app` in any outer Starlette router breaks the MCP lifespan (confirmed by the existing code comment at line ~349). Prefix dispatch inside the middleware is the established pattern.

### D3: UI proxy — no cookie injection, pass-through headers

The UI proxy target is a browser-rendered app. Injecting the internal `mc_token_5476` session cookie would bypass the crew's own login UI and could create confusing authenticated-but-wrong-user states if the cookie has expired. The spec requires the browser to go through the normal login flow.

**Decision**: UI proxy passes request headers as-is (minus `host`, which must be rewritten to the upstream target). No `Cookie` header is added or removed.

### D4: API proxy — inject internal session cookie

REST callers using `/crews/{id}/api/` are operators or automation that know the crew exists and expect to talk directly to its gateway. Requiring them to separately obtain a `mc_token_5476` cookie would be impractical.

**Decision**: API proxy reads `crew["cookie"]` from the registry and injects `Cookie: mc_token_5476=<value>`. If the upstream returns 401/403, the handler attempts a single cookie refresh via `_refresh_cookie` and retries — the same phase-1 recovery that `_crew_api_with_recovery` applies. No full restart is attempted from the proxy handler itself (the auto-wake before forwarding already handles dead containers).

### D5: Response streaming via httpx async streaming API

`httpx.AsyncClient.stream()` returns an async context manager that yields chunks without buffering the full body. Starlette's `StreamingResponse` accepts an `async_generator`.

**Decision**: proxy handlers use `async with _async_http.stream(method, url, ...) as resp` and yield chunks to a `StreamingResponse`. Hop-by-hop headers (`transfer-encoding`, `connection`, `keep-alive`, `te`, `trailers`, `upgrade`) are stripped from the forwarded response before passing to the client, following standard proxy practice.

## Risks / Trade-offs

- **Streaming large responses**: The streaming design avoids in-memory buffering, but very large responses (e.g. log downloads from the UI) will hold an httpx connection open for the full transfer duration. The 60 s timeout applies end-to-end; operators downloading large artifacts should use `evac` instead.  
  → Mitigation: document the timeout in the reference; the same constraint applies to file transfer today.

- **Stale cookie on API proxy**: The API proxy injects a cookie but does not handle the full two-phase recovery that `_crew_api_with_recovery` does. A stopped crew that was just woken may have a stale cookie before the transport has refreshed it.  
  → Mitigation: `_ensure_crew_running` already refreshes the cookie on restart (line ~1825 in server.py). The single-retry on 401/403 in the proxy handler covers the residual race.

- **Path parsing brittleness**: splitting on `/` rather than using a router means the crew_id must not contain `/`. That constraint already exists (crew IDs are lowercase alphanumeric+hyphen, enforced at launch).

## Migration Plan

No migration needed — the new routes are purely additive. No existing routes change. `BearerAuthMiddleware` gains two new prefix checks that are only reached after existing prefix checks, so no existing behaviour is affected.

Deployment: standard transport image rebuild and restart. No database migration, no volume change.

## Open Questions

None — all design decisions are resolved above.
