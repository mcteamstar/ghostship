# Dashboard Proxy

Each crew has a KiroCrew gateway UI — a full chat and task management interface. The **dashboard proxy** makes it accessible in a browser without any separate server setup.

## How it works

When a crew is launched, the transport allocates a dedicated port from a configurable range (default `64058–64107`) and starts a lightweight reverse proxy on that port. All requests on that port are forwarded to the crew's internal gateway (`http://gs-{crew_id}:5476`) over the ghost-academy Podman network.

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

`launch` returns a `dashboard_url` in its response:

```json
{
  "crew_id": "my-crew",
  "dashboard_url": "http://academy.example.com:64058/",
  ...
}
```

`crews` also includes `dashboard_url` per crew (null for crews launched before this feature or when `GA_DASHBOARD_PORT_ENABLED=false`).

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

**The dashboard proxy is not currently gated by `GA_API_KEY`.** The transport's bearer-token auth applies to MCP tool calls (port 64057 / the main transport port), but browser requests to the UI ports do not carry an `Authorization` header.

What protects the UI ports:

- **Network layer** — on a Tailscale deployment, only devices on your tailnet can reach the host. This is the primary access control.
- **Session cookie** — the injected `mc_token_5476` cookie is scoped to the crew's gateway and signed. A visitor without the cookie sees an onboarding screen and cannot interact with the crew. The cookie is set HttpOnly and SameSite=Lax.

**Recommendation:** For any deployment reachable from the public internet, set `GA_DASHBOARD_PORT_ENABLED=false` or restrict the port range at your firewall/security group until per-port bearer-token auth is implemented.

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

## Limitations

- **Port exhaustion** — if all 50 ports are allocated, `launch` returns an error. Increase `GA_DASHBOARD_PORT_RANGE_SIZE` if you need more concurrent crew UIs.
- **No `GA_API_KEY` gating** — see Security above.
- **Port collisions** — if the chosen range conflicts with other services on your host, change `GA_DASHBOARD_PORT_RANGE_START` in your config.
