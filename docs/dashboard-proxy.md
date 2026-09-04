# Dashboard Proxy

Each crew has a KiroCrew gateway UI — a full chat and task management interface. The **dashboard proxy** makes it accessible in a browser.

> **TRN-103 BREAKING CHANGE:** `ga-portal` (Portal) is now a required component and is always installed — `GA_PORTAL_ENABLED` was removed. Dashboard proxying is exclusively handled by Portal (`ga-portal`); the transport's per-port uvicorn proxy threads no longer exist. See [Migration](#migration) if you are upgrading.

## Requirements

Portal (`ga-portal`) is always present, so any crew launched with `dashboard=True` gets a dashboard. Crews launched without `dashboard=True` (the default) are headless — no dashboard is allocated and no Portal registration is needed for those crews.

## How it works

When a dashboard is requested, the transport allocates a dedicated port from the configured range (default `64058–64107`) and registers it with Portal (Caddy) via the admin API.

```
Browser → host:64058 (HTTPS, via ga-portal)
        → forward_auth check at ga-transport:8000/dashboard-auth
        → (on valid gs_session cookie) reverse_proxy → ga-transport:8000
              rewrite → /crews/{crew_id}/ui/{original_path}
        → transport injects Cookie: mc_token_5476=<crew_token>
        → gs-{crew_id}:5476
```

> **TRN-102:** Caddy no longer proxies dashboard traffic to `gs-{crew_id}:5476` directly. It routes to the transport's cookie-injecting UI-proxy endpoint (`/crews/{crew_id}/ui/`), which forwards to the crew gateway. This resolves the **403 — IP mismatch** the gateway returned when the session cookie (minted from `ga-transport`'s IP) was presented on a request arriving from `ga-portal`'s IP: with TRN-102 the crew gateway is reached exclusively from `ga-transport`, so the cookie's IP binding is always satisfied.

Key properties:

- **Portal (`ga-portal`) owns all dashboard port bindings.** The transport no longer binds these ports directly.
- **Caddy talks only to `ga-transport:8000`.** Both the MCP/file routes and the per-crew dashboard routes upstream to `ga-transport:8000`. Caddy has no network path to crew containers (`gs-*`) — see [Network topology](#network-topology).
- **The transport injects the session cookie.** The `mc_token_5476` cookie is added by the transport's UI-proxy endpoint (not by the Caddy config), from `ga-transport`'s own IP. The cookie is transparently re-minted when it is within 20% of its TTL of expiring, so sessions never see a "Session expired" prompt.
- **WebSocket connections are proxied.** Real-time chat/task streaming over WebSocket is upgraded and bidirectionally relayed through the same `/crews/{crew_id}/ui/` endpoint.
- **Crew containers are untouched.** They only expose port 5476 on the internal Podman network.
- **TLS on every port.** Caddy terminates HTTPS on the main port (443) and on every per-crew dashboard port. See [caddy.md — TLS modes](caddy.md#tls-modes).
- **`gs_session` cookie gate.** When `GA_API_KEY` is set, every dashboard port requires a valid `gs_session` cookie issued by `/dashboard-login`. Unauthenticated requests redirect to the login page (`/login-ui`).
- **Dashboard URLs are HTTPS.** `launch(dashboard=True)` returns `https://host:PORT/` (or `http://host:PORT/` when `GA_PORTAL_TLS_MODE=off`). The `dashboard_url` shape is unchanged by TRN-102.
- **CORS is pre-configured.** The UI port origin (`{scheme}://{host}:{dashboard_port}`) is added to `KIROCREW_CORS_ORIGINS` at container create time. This is the origin the browser uses, so the SPA's API calls are accepted; the transport's internal port (8000) is never a browser-facing origin and needs no CORS entry.
- **SPA navigation works correctly.** Because the SPA owns a full origin, `history.pushState` navigation, hard reloads, and link sharing all work as expected.

## Network topology

`ga-net` (the internal Podman network) is reserved for **transport ↔ crew container** traffic:

- `ga-transport` is on `ga-net` (to reach `gs-*` crew gateways) **and** the compose default network (so `ga-portal` can dial it).
- `ga-portal` (Caddy) is **not** on `ga-net`. It reaches `ga-transport:8000` over the compose default network and has no route to any crew container. The trust boundary — the external-facing proxy cannot touch crew gateways directly — is enforced by network topology, not just config.

## Setup

Portal is installed automatically by `install.sh` — no flag is required. Set the TLS mode as needed:

```bash
# ghostship.conf
GA_PORTAL_TLS_MODE=internal   # or tailscale / acme / off
```

```bash
./install.sh --config ./ghostship.conf
```

For `GA_PORTAL_TLS_MODE=internal` (default): run `caddy trust` once to trust the CA. The exact command is printed by `install.sh` and `ghostship status`.

See [caddy.md](caddy.md) for full setup, TLS modes, and auth configuration.

## The `dashboard_url`

When launched with `dashboard=True`, `launch` returns a `dashboard_url`:

```json
{
  "crew_id": "my-crew",
  "dashboard_url": "https://academy.example.com:64058/",
  ...
}
```

A crew launched headless (the default) has `dashboard_url: null` in its response.

`crews` also includes `dashboard_url` per crew (`null` for headless crews or crews launched before this feature).

## Managing dashboard allocation after launch

A headless crew can be given a dashboard later — and a dashboard can be released — through two REST endpoints on the transport port. Both require the `Authorization: Bearer <key>` header when `GA_API_KEY` is set.

**`POST /crews/{crew_id}/dashboard`** — allocate a UI port, register with Portal, and store `dashboard_port` in the registry. Returns `{"dashboard_url": "..."}`. No-op if the crew already has a dashboard.

```bash
curl -sX POST http://localhost:64057/crews/my-crew/dashboard | jq
# → { "dashboard_url": "https://localhost:64058/" }
```

**`DELETE /crews/{crew_id}/dashboard`** — deregister from Portal, release the port, and clear `dashboard_port` from the registry. Returns `{"dashboard_url": null}`. No-op if the crew has no dashboard.

```bash
curl -sX DELETE http://localhost:64057/crews/my-crew/dashboard | jq
# → { "dashboard_url": null }
```

## Configuration

| Variable | Default | Description |
|:---------|:--------|:------------|
| `GA_DASHBOARD_PORT_RANGE_START` | `64058` | First port in the UI port range |
| `GA_DASHBOARD_PORT_RANGE_SIZE` | `50` | Number of ports (max concurrent crew dashboards) |

> `GA_DASHBOARD_PORT_ENABLED` was removed in TRN-101, and `GA_PORTAL_ENABLED` was removed in TRN-103 — Portal is always installed.

See [caddy.md](caddy.md) for all Portal-related options (`GA_PORTAL_TLS_MODE`, `GA_PORTAL_DOMAIN`, etc.).

## Firewall

The UI port range must be reachable from your browser. On a Tailscale deployment:

```bash
sudo ufw allow 64058:64107/tcp
```

`install.sh` adds this rule automatically.

## Port persistence across restarts

Allocated ports are stored in `crews.json`. When the transport restarts, it reads the registry and re-registers all existing crew ports with Caddy (idempotent), so existing dashboard URLs continue to work without re-launching the crew.

## Migration

For deployments upgrading from a pre-TRN-103 install that had `GA_PORTAL_ENABLED=false` (or the older per-port proxy mode):

1. Remove any `GA_PORTAL_ENABLED` line from `ghostship.conf` — it is ignored; Portal is always installed.
2. Re-run `install.sh` — `ga-portal` is added to the compose stack and takes over the dashboard ports.
3. If `GA_PORTAL_TLS_MODE=internal` (default): run `caddy trust` once to trust the CA.
4. Existing crews that had dashboard ports will need to be nuked and re-launched so Portal registers them at their new HTTPS URLs.

For fresh installs, no action is needed — Portal is set up by `install.sh`.

## Limitations

- **Port exhaustion** — if all 50 ports are allocated, `launch` returns an error. Increase `GA_DASHBOARD_PORT_RANGE_SIZE` if you need more concurrent crew UIs.
- **Port collisions** — if the chosen range conflicts with other services on your host, change `GA_DASHBOARD_PORT_RANGE_START` in your config.
