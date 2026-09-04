# Dashboard Proxy

Each crew has a KiroCrew gateway UI — a full chat and task management interface. The **dashboard proxy** makes it accessible in a browser without any separate server setup.

## How it works

Dashboards are **opt-in**. Crews are headless by default: `launch(crew_id)` allocates no port and returns no `dashboard_url`. To get a dashboard, launch with `dashboard=True` (and `GA_DASHBOARD_PORT_ENABLED=true`, the default). You can also attach or detach a dashboard after launch via the REST API (see [Managing dashboard allocation after launch](#managing-dashboard-allocation-after-launch)).

When a dashboard is requested, the transport allocates a dedicated port from a configurable range (default `64058–64107`) and starts a lightweight reverse proxy on that port. All requests on that port are forwarded to the crew's internal gateway (`http://gs-{crew_id}:5476`) over the ghost-academy Podman network.

```
Browser → host:64058
        → transport process (daemon thread, own event loop)
        → gs-{crew_id}:5476  (internal Podman network, never exposed)
```

Key properties:

- **Crew containers are untouched.** They only expose port 5476 on the internal Podman network, exactly as before.
- **The transport owns all UI ports.** No Podman port bindings on crew containers; no Caddy involvement.
- **Session auth is injected automatically.** The transport holds the crew's session cookie (`mc_token_5476`) from launch time and injects it as a `Set-Cookie` header on every proxied response, so the browser is authenticated without a manual login flow.
- **CORS is pre-configured.** The UI port origin (e.g. `http://academy.example.com:64058`) is added to `KIROCREW_CORS_ORIGINS` at container create time so the SPA's API calls are not rejected.
- **SPA navigation works correctly.** Because the SPA owns a full origin (`host:64058/`) rather than a path prefix, `history.pushState` navigation, hard reloads, and link sharing all work as expected.

## The `dashboard_url`

When launched with `dashboard=True`, `launch` returns a `dashboard_url` in its response:

```json
{
  "crew_id": "my-crew",
  "dashboard_url": "http://academy.example.com:64058/",
  ...
}
```

A crew launched headless (the default) has no `dashboard_url` in its `launch` response.

`crews` also includes `dashboard_url` per crew (null for crews launched headless, launched before this feature, or when `GA_DASHBOARD_PORT_ENABLED=false`).

## Managing dashboard allocation after launch

A headless crew can be given a dashboard later — and a dashboard can be released — through two REST endpoints on the transport port. Both require the `Authorization: Bearer <key>` header when `GA_API_KEY` is set, like all other transport routes.

**`POST /crews/{crew_id}/dashboard`** — allocate a UI port, start the proxy listener, and store `dashboard_port` in the registry. Returns `{"dashboard_url": "..."}`. No-op if the crew already has a dashboard — returns the existing `dashboard_url`.

```bash
curl -sX POST http://localhost:64057/crews/my-crew/dashboard | jq
# → { "dashboard_url": "http://localhost:64058/" }
```

**`DELETE /crews/{crew_id}/dashboard`** — stop the proxy listener, release the port, and clear `dashboard_port` from the registry. Returns `{"dashboard_url": null}`. No-op (also returns `{"dashboard_url": null}`) if the crew has no dashboard.

```bash
curl -sX DELETE http://localhost:64057/crews/my-crew/dashboard | jq
# → { "dashboard_url": null }
```

## Configuration

| Variable | Default | Description |
|:---------|:--------|:------------|
| `GA_DASHBOARD_PORT_ENABLED` | `true` | Enable/disable the dashboard proxy entirely |
| `GA_DASHBOARD_PORT_RANGE_START` | `64058` | First port in the UI port range |
| `GA_DASHBOARD_PORT_RANGE_SIZE` | `50` | Number of ports (max concurrent crew UIs) |

Set `GA_DASHBOARD_PORT_ENABLED=false` to disable port allocation and fall back to the previous path-prefix proxy (`/crews/{id}/ui/`).

## Firewall

The UI port range must be reachable from your browser. On a Tailscale deployment, add a firewall rule on the host:

```bash
sudo ufw allow 64058:64107/tcp
```

The `install.sh` script adds this rule automatically.

For a cloud deployment with a security group, open the equivalent port range inbound from your IP.

## Security

> ⚠️ **Dashboard ports are unauthenticated when Caddy is disabled.** Anyone who can reach the port can open the crew UI. Restrict access at the network layer (Tailscale, firewall, security group). For full authentication, enable the Caddy layer — see [Caddy mode](#caddy-mode) below.

**The dashboard proxy is not currently gated by `GA_API_KEY` when Caddy is disabled.** The transport's bearer-token auth applies to MCP tool calls (port 64057 / the main transport port), but browser requests to the UI ports do not carry an `Authorization` header — and there is no other credential check.

What protects the UI ports in direct mode:

- **Network layer** — on a Tailscale deployment, only devices on your tailnet can reach the host. This is the primary access control.
- **Session cookie** — the injected `mc_token_5476` cookie is scoped to the crew's gateway and signed. A visitor without the cookie sees an onboarding screen and cannot interact with the crew. The cookie is set HttpOnly and SameSite=Lax. Note: the cookie is set on every response, so any visitor who loads the page receives it.

**Recommendation:** Only enable `GA_DASHBOARD_PORT_ENABLED=true` on deployments protected by Tailscale or a network-level firewall. For any deployment reachable from the public internet, enable `GA_PORTAL_ENABLED=true` (see [Caddy mode](#caddy-mode)) or set `GA_DASHBOARD_PORT_ENABLED=false`.

## Caddy mode

> ⚠️ **Breaking change — clean cutover.** Setting `GA_PORTAL_ENABLED=true` moves the dashboard port bindings from the transport to Caddy. There is no coexistence window. Re-run `install.sh` after changing the flag. The per-port uvicorn listener threads are not started when Caddy is enabled.

When `GA_PORTAL_ENABLED=true`, Caddy takes over all dashboard port bindings and adds authentication to every dashboard port:

```
Browser → host:64058 (HTTPS, via ga-portal)
        → forward_auth check at ga-transport:/dashboard-auth
        → (on valid gs_session cookie) reverse_proxy → gs-{crew_id}:5476
```

Key differences from direct mode:

- **TLS on every port.** Caddy terminates HTTPS on the main port (443) and on every per-crew dashboard port. See [caddy.md — TLS modes](caddy.md#tls-modes) for `internal` / `tailscale` / `acme` / `off`.
- **`gs_session` cookie gate.** Every dashboard port requires a valid `gs_session` cookie issued by `/dashboard-login`. Unauthenticated requests redirect to the login page (`/login-ui`).
- **No per-port uvicorn threads.** Caddy handles the port binding; the transport manages the port pool and registers/deregisters Caddy servers via the admin API when crews launch/nuke.
- **Dashboard URLs are HTTPS.** `launch(dashboard=True)` returns `https://host:64058/` when Caddy is enabled.

See [caddy.md](caddy.md) for setup, TLS modes, auth upgrade paths, and migration instructions.

## Port persistence across restarts

Allocated ports are stored in `crews.json`. When the transport restarts, it reads the registry and re-starts the daemon-thread proxy servers for any crews that have a `dashboard_port` assigned, so existing UI URLs continue to work without re-launching the crew.

## How the proxy session works

Under the hood, each UI port runs a `uvicorn` server in a daemon thread with its own asyncio event loop. The proxy handler:

1. Reads the crew's session cookie from the registry
2. Merges it with any cookie the browser already has
3. Forwards the full request (method, path, query, headers, body) to the crew gateway
4. Strips `content-encoding` and `content-length` (httpx decompresses transparently)
5. Sets `Set-Cookie: mc_token_5476=...` on the response so the browser persists the session

This means each page load — including sub-routes and hard reloads — carries the correct session.

**WebSocket proxying.** The same per-port proxy also handles WebSocket upgrades: the handler detects a `websocket` scope, opens an upstream connection to the crew gateway via `httpx-ws` (`aconnect_ws`), and bidirectionally relays text and binary frames between the browser and the gateway until either side disconnects. This is what makes the KiroCrew dashboard's real-time features (live task/chat streaming) work through the proxy, not just plain HTTP request/response.

## Limitations

- **Port exhaustion** — if all 50 ports are allocated, `launch` returns an error. Increase `GA_DASHBOARD_PORT_RANGE_SIZE` if you need more concurrent crew UIs.
- **No `GA_API_KEY` gating** — see Security above.
- **Port collisions** — if the chosen range conflicts with other services on your host, change `GA_DASHBOARD_PORT_RANGE_START` in your config.
