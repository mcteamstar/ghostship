## Context

See proposal.md — Why for motivation.

The KiroCrew gateway UI is a React SPA designed to own the entire origin. Path-prefix proxying breaks `window.history.pushState`. Subdomain routing requires wildcard DNS/TLS. Direct Podman port binding bypasses all transport security. The solution is the transport itself listening on a range of ports — one per allocated crew UI — and reverse-proxying to the appropriate crew gateway. All existing transport security (auth, rate limiting, logging) applies automatically because it's the same process.

**Crew containers are completely unchanged.** They continue to expose only port 5476 on the internal ghost-academy Podman network, unreachable from the host or the internet. The transport already communicates with crew containers over this network for all other operations (dispatch, pickup, evac, etc.) — the UI proxy is just another consumer of the same internal route. No Podman port bindings, no firewall changes on the crew side, nothing new in the crew image.

The transport already runs under uvicorn. Rather than sharing the MCP app (which can only be started once due to its `StreamableHTTPSessionManager`), each dashboard port gets its own lightweight ASGI callable in a dedicated daemon thread with its own `asyncio` event loop. At crew launch the transport starts a new server bound to the allocated port; at nuke it stops it. Each per-port ASGI callable handles auth, HTTP proxying via httpx, and WebSocket proxying via httpx-ws.

## Goals / Non-Goals

**Goals:**
- SPA assets, client-side navigation, and hard reloads all work correctly.
- All transport security (GA_API_KEY auth, rate limiting) applies to UI traffic.
- No Caddy config changes, no Podman port bindings, no additional infrastructure.
- Routes registered/removed automatically at launch/nuke.

**Non-Goals:**
- TLS per-crew port (all ports share the transport's TLS config).
- Subdomain-per-crew routing.

## Decisions

**D1: Transport spawns a daemon thread per crew UI port**

At launch (when `dashboard=True`), after the crew container is started, the transport spawns a daemon `threading.Thread` for each UI port. Each thread runs its own `asyncio.run()` event loop with a dedicated lightweight uvicorn server bound to `0.0.0.0:{dashboard_port}`. The server uses a bare ASGI callable (not the MCP app — the MCP `StreamableHTTPSessionManager` can only be started once per instance). The proxy callable handles auth, session cookie injection, and proxying to the crew gateway using a fresh `httpx.AsyncClient()` per request (required because the daemon thread's event loop is separate from the main transport event loop).

`_dashboard_port_servers: dict[int, uvicorn.Server]` and `_dashboard_port_crew: dict[int, str]` track active servers and the port→crew_id mapping. At nuke, `server.should_exit = True` signals shutdown and both dicts are cleaned up.

The per-port proxy app enforces `GA_API_KEY` auth independently (via constant-time comparison) since browser requests don't share the main transport's `BearerAuthMiddleware` ASGI context.

Alternatives considered:
- *Shared main event loop via `create_task`*: Doesn't work — `uvicorn.Server.serve()` monopolises the event loop and tasks never run.
- *`asyncio.run_coroutine_threadsafe`*: Schedules on the main loop but same problem — the main uvicorn server blocks it.
- *Podman port binding (previous approach)*: Direct binding to host bypasses all transport security. Rejected.
- *Caddy dynamic proxy per port*: Adds infrastructure complexity. Rejected.

**D2: Port-to-crew mapping via module-level dict**

`_dashboard_port_crew: dict[int, str]` maps allocated port → crew_id. The catch-all proxy handler reads this dict to find the crew for any incoming request. Populated at launch, cleared at nuke, restored from `crews.json` at startup.

**D3: Port allocation and registry persistence (unchanged from previous approach)**

`_dashboard_ports_in_use: set[int]` tracks allocated ports. `_allocate_dashboard_port()` scans the range for the first free port. Port and `dashboard_url` stored in `crews.json`. Restored at startup.

At startup, the transport also restarts the per-port uvicorn servers for any crews that already have a `dashboard_port` in the registry (handles transport restarts).

**D4: CORS injection includes UI port origin**

`KIROCREW_CORS_ORIGINS` is built at `container_create` time with two origins: the transport's public origin (from `GA_HOST_URL` or `http://localhost:{PORT}`) and the allocated UI port origin (e.g. `http://academy.example.com:64058`). The port origin must be added separately after allocation since `dashboard_port` isn't known until after `_allocate_dashboard_port()` runs. Without the port origin, the SPA's API calls from the browser are CSRF-rejected by the crew gateway.

**D5: Session cookie injection**

The transport stores the crew's session cookie (`mc_token_5476`) in `crews.json` at launch time (minted via `_mint_cookie`). The UI port proxy injects this as a `Set-Cookie` header on every proxied response, so the browser is automatically authenticated without going through a manual kiro-cli device auth flow. Without this, the gateway shows the "install kiro-cli" onboarding screen even though auth is already injected into the container's kiro-cli DB.

**D6: WebSocket proxying — httpx-ws**

The current `_proxy_asgi` ASGI callable ignores `scope["type"] == "websocket"` requests, returning nothing and causing uvicorn to send a 400/403 to the browser. The KiroCrew SPA requires a persistent WebSocket connection to `/api/ws` for real-time session updates — without it the gateway shows "offline".

httpx does not support WebSocket connections. The correct solution is `httpx-ws` (`pip install httpx-ws`), which wraps httpx with WebSocket support via `aconnect_ws`. The proxy ASGI callable must handle both `scope["type"] == "http"` (existing path) and `scope["type"] == "websocket"` (new path).

WebSocket proxy pattern using Starlette's `WebSocket` and `httpx-ws`:
1. Accept the incoming WS connection from the browser (`websocket.accept()`)
2. Open an outbound WS connection to the upstream crew gateway via `aconnect_ws`
3. Bidirectionally pump messages between the two connections concurrently using `asyncio.gather`
4. Forward the session cookie in the upstream connection request headers
5. Handle disconnection from either side gracefully

The daemon thread has its own event loop, so `aconnect_ws` runs in the correct context without conflicts with the main transport event loop.

`httpx-ws` must be added to `transport/requirements.txt` (pin to current latest, `0.7.0`).

**D7: `/api/instances` 403 — KiroCrew feature flag, not auth failure**

Investigation showed that `/api/instances` returns HTTP 403 but with body `{"error": "instances feature is disabled (set instances.enabled=true)"}`. This is a KiroCrew feature flag, not a cookie auth failure. The session cookie is being forwarded and accepted correctly — other authenticated endpoints (`/api/agents`, `/api/sessions`) return 200.

The 403 on `/api/instances` is expected behaviour from the KiroCrew gateway. The "Gateway offline" status in the browser is caused entirely by the WebSocket failure (D6), not by this 403. No action required for `/api/instances`.

## Risks / Trade-offs

- **Many open ports** → The UI port range (default 64058–64107) must be open in `ufw` and accessible via Tailscale/firewall. This is 50 ports, but they're all on the same host and protected by the transport's `GA_API_KEY` auth. Acceptable.
- **Uvicorn sub-server startup time** → Each `uvicorn.Server.startup()` takes ~100ms. Launch is already not instant, so this is negligible.
- **Event loop blocking on server shutdown** → `server.should_exit = True` is non-blocking; the server drains in-flight requests gracefully. Nuke should await shutdown with a short timeout before proceeding.
- **Port pool exhaustion** → Launch returns an error if all 50 ports are allocated. Default range of 50 is generous for typical use.

## Migration Plan

1. Add `ufw allow 64058:64107/tcp` in `ohnomer/servers/hyperv/academy/install.sh` (done).
2. Deploy updated transport.
3. Existing live crews without a `dashboard_port` can retrofit via `POST /crews/{id}/dashboard` — no nuke required.
4. Rollback: set `GA_DASHBOARD_PORT_ENABLED=false` — skips port allocation entirely, no UI ports opened.
