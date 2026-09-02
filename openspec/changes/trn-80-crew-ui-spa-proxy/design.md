## Context

See proposal.md — Why for motivation.

The KiroCrew gateway UI is a React SPA designed to own the entire origin. Path-prefix proxying breaks `window.history.pushState`. Subdomain routing requires wildcard DNS/TLS. Direct Podman port binding bypasses all transport security. The solution is the transport itself listening on a range of ports — one per allocated crew UI — and reverse-proxying to the appropriate crew gateway. All existing transport security (auth, rate limiting, logging) applies automatically because it's the same process.

**Crew containers are completely unchanged.** They continue to expose only port 5476 on the internal ghost-academy Podman network, unreachable from the host or the internet. The transport already communicates with crew containers over this network for all other operations (dispatch, pickup, evac, etc.) — the UI proxy is just another consumer of the same internal route. No Podman port bindings, no firewall changes on the crew side, nothing new in the crew image.

The transport already runs under uvicorn. Uvicorn supports serving a Starlette app on multiple ports via separate `asyncio` server instances in the same event loop. At crew launch the transport starts a new server bound to the allocated port; at nuke it stops it. All port-bound servers share the same app router but the incoming port is used to look up the target crew.

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

**D1: Transport binds additional uvicorn servers per crew UI port**

At launch, after the crew container is started, the transport calls `uvicorn.Server` with a `uvicorn.Config` bound to `0.0.0.0:{ui_port}` and starts it in the background within the existing asyncio event loop. The server uses the same Starlette app instance. All incoming requests on that port pass through `BearerAuthMiddleware` (GA_API_KEY check), rate limiting, and then a port-based catch-all handler that looks up the crew by port and proxies to `http://gs-{crew_id}:5476/{path}`.

At nuke, the transport calls `server.should_exit = True` on the per-port server, waits for shutdown, and releases the port.

Per-port server handles are stored in a module-level dict `_ui_port_servers: dict[int, uvicorn.Server]` keyed by port.

Alternatives considered:
- *Podman port binding (previous approach)*: Direct binding to host bypasses all transport security. Rejected.
- *Caddy dynamic proxy per port*: Adds infrastructure complexity and another hop. Rejected.
- *Caddy pre-configured for all 50 ports forwarding to transport*: Unnecessary middleman — the transport can own the ports directly.

**D2: Port-to-crew mapping via module-level dict**

`_ui_port_crew: dict[int, str]` maps allocated port → crew_id. The catch-all proxy handler reads this dict to find the crew for any incoming request. Populated at launch, cleared at nuke, restored from `crews.json` at startup.

**D3: Port allocation and registry persistence (unchanged from previous approach)**

`_ui_ports_in_use: set[int]` tracks allocated ports. `_allocate_ui_port()` scans the range for the first free port. Port and `ui_url` stored in `crews.json`. Restored at startup.

At startup, the transport also restarts the per-port uvicorn servers for any crews that already have a `ui_port` in the registry (handles transport restarts).

**D4: CORS injection at container create (unchanged)**

`KIROCREW_CORS_ORIGINS` is appended with the transport's public origin so the SPA's API calls to the crew gateway aren't CORS-rejected.

## Risks / Trade-offs

- **Many open ports** → The UI port range (default 64058–64107) must be open in `ufw` and accessible via Tailscale/firewall. This is 50 ports, but they're all on the same host and protected by the transport's `GA_API_KEY` auth. Acceptable.
- **Uvicorn sub-server startup time** → Each `uvicorn.Server.startup()` takes ~100ms. Launch is already not instant, so this is negligible.
- **Event loop blocking on server shutdown** → `server.should_exit = True` is non-blocking; the server drains in-flight requests gracefully. Nuke should await shutdown with a short timeout before proceeding.
- **Port pool exhaustion** → Launch returns an error if all 50 ports are allocated. Default range of 50 is generous for typical use.

## Migration Plan

1. Add `ufw allow 64058:64107/tcp` in `ohnomer/servers/hyperv/academy/install.sh`.
2. Deploy updated transport.
3. Existing live crews have no `ui_port` — they need to be nuked and re-launched to get a UI port. Or the startup reconciliation will register them on next transport restart.
4. Rollback: set `GA_UI_PORT_ENABLED=false` — skips port allocation entirely, no UI ports opened.
