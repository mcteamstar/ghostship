## Why

Crew containers run the KiroCrew gateway UI on port 5476 (internal to ga-net), but that port is unreachable from the host — only the transport's single outward-facing port is published. When debugging long-running SDD tasks it is currently impossible to inspect agent turns, tool calls, or in-flight mail without exec'ing into the container. The transport already knows how to reach every crew and already auto-wakes stopped crews; it should also proxy the crew's own UI and REST API for operators who need that visibility.

## What Changes

- **New route `GET /crews/{crew_id}/ui` and `GET/POST/DELETE /crews/{crew_id}/ui/{path:path}`**: reverse-proxy all requests (headers, body, streaming) to `http://gs-{crew_id}:5476/`, auto-waking the crew if stopped.
- **New route `GET/POST/DELETE/PUT/PATCH /crews/{crew_id}/api/{path:path}`**: reverse-proxy to `http://gs-{crew_id}:5476/api/{path}`, forwarding the request method, headers, and body unchanged. Useful for direct REST calls without going through MCP tools.
- **Auth enforcement**: both proxy routes respect `GA_API_KEY` — they sit behind `BearerAuthMiddleware` and require the bearer token when a key is configured.
- **Auto-wake**: both routes call `_ensure_crew_running` before proxying, consistent with all other crew-touching endpoints.
- **No cookie injection for UI proxy**: the UI is a browser-facing resource; the transport passes the request through as-is rather than injecting the internal session cookie (the browser gets the login page if needed).
- **Cookie injection for API proxy**: the `/crews/{crew_id}/api/` proxy forwards the internal session cookie so REST calls work without a separate browser login.
- **`BearerAuthMiddleware` routing extended** to recognise the new `/crews/*/ui*` and `/crews/*/api/` path prefixes and dispatch them to a new `ProxyCrew` ASGI handler.

## Capabilities

### New Capabilities

_(none — the behaviour is an extension of existing proxy-hosting)_

### Modified Capabilities

- `proxy-hosting`: The transport gains two new reverse-proxy route families (`/crews/{id}/ui/` and `/crews/{id}/api/`) that tunnel requests to crew gateway containers. This is spec-level behaviour (new externally-visible endpoints with defined auth and auto-wake semantics).

## Impact

- `transport/server.py`: new async handler functions and wiring into `BearerAuthMiddleware.__call__`.
- `transport/requirements.txt`: no new dependencies — `httpx` is already present and supports streaming proxies.
- No breaking changes to existing MCP tools or REST routes.
- Docs: `docs/reference.md` should document the two new route families and their auth behaviour.
