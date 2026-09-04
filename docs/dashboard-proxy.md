# Dashboard Proxy

Each crew has a KiroCrew gateway UI — a full chat and task management interface. The **dashboard proxy** makes it accessible in a browser.

> **TRN-101 BREAKING CHANGE:** `launch(dashboard=True)` now requires `GA_PORTAL_ENABLED=true`. The transport's per-port uvicorn proxy threads are removed. Dashboard proxying is exclusively handled by Portside (`ga-portal`). See [Migration](#migration) if you are upgrading.

## Requirements

`GA_PORTAL_ENABLED=true` is required for any crew dashboard. When Portside is disabled, `launch(dashboard=True)` returns an error:

```
"dashboard access requires GA_PORTAL_ENABLED=true; re-run install.sh
and re-launch any existing dashboard crews — see docs/dashboard-proxy.md"
```

Crews launched without `dashboard=True` (the default) are headless — no dashboard is allocated and no Portside registration is needed for those crews.

## How it works

When a dashboard is requested and `GA_PORTAL_ENABLED=true`, the transport allocates a dedicated port from the configured range (default `64058–64107`) and registers it with Portside (Caddy) via the admin API.

```
Browser → host:64058 (HTTPS, via ga-portal)
        → forward_auth check at ga-transport:/dashboard-auth
        → (on valid gs_session cookie) reverse_proxy → gs-{crew_id}:5476
```

Key properties:

- **Portside (`ga-portal`) owns all dashboard port bindings.** The transport no longer binds these ports directly.
- **Crew containers are untouched.** They only expose port 5476 on the internal Podman network.
- **TLS on every port.** Caddy terminates HTTPS on the main port (443) and on every per-crew dashboard port. See [caddy.md — TLS modes](caddy.md#tls-modes).
- **`gs_session` cookie gate.** Every dashboard port requires a valid `gs_session` cookie issued by `/dashboard-login`. Unauthenticated requests redirect to the login page (`/login-ui`).
- **Dashboard URLs are HTTPS.** `launch(dashboard=True)` returns `https://host:PORT/` (or `http://host:PORT/` when `GA_PORTAL_TLS_MODE=off`).
- **CORS is pre-configured.** The UI port origin is added to `KIROCREW_CORS_ORIGINS` at container create time.
- **SPA navigation works correctly.** Because the SPA owns a full origin, `history.pushState` navigation, hard reloads, and link sharing all work as expected.

## Setup

Enable Portside and re-run `install.sh`:

```bash
# ghostship.conf
GA_PORTAL_ENABLED=true
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

**`POST /crews/{crew_id}/dashboard`** — allocate a UI port, register with Portside, and store `dashboard_port` in the registry. Returns `{"dashboard_url": "..."}`. No-op if the crew already has a dashboard. Returns 503 if `GA_PORTAL_ENABLED=false`.

```bash
curl -sX POST http://localhost:64057/crews/my-crew/dashboard | jq
# → { "dashboard_url": "https://localhost:64058/" }
```

**`DELETE /crews/{crew_id}/dashboard`** — deregister from Portside, release the port, and clear `dashboard_port` from the registry. Returns `{"dashboard_url": null}`. No-op if the crew has no dashboard.

```bash
curl -sX DELETE http://localhost:64057/crews/my-crew/dashboard | jq
# → { "dashboard_url": null }
```

## Configuration

| Variable | Default | Description |
|:---------|:--------|:------------|
| `GA_PORTAL_ENABLED` | `false` | **Required for dashboard access.** Enable the Caddy reverse-proxy layer |
| `GA_DASHBOARD_PORT_RANGE_START` | `64058` | First port in the UI port range |
| `GA_DASHBOARD_PORT_RANGE_SIZE` | `50` | Number of ports (max concurrent crew dashboards) |

> `GA_DASHBOARD_PORT_ENABLED` was removed in TRN-101. Use `GA_PORTAL_ENABLED=true` instead.

See [caddy.md](caddy.md) for all Portside-related options (`GA_PORTAL_TLS_MODE`, `GA_PORTAL_DOMAIN`, etc.).

## Firewall

The UI port range must be reachable from your browser. On a Tailscale deployment:

```bash
sudo ufw allow 64058:64107/tcp
```

`install.sh` adds this rule automatically.

## Port persistence across restarts

Allocated ports are stored in `crews.json`. When the transport restarts, it reads the registry and re-registers all existing crew ports with Caddy (idempotent), so existing dashboard URLs continue to work without re-launching the crew.

## Migration

For deployments upgrading from the pre-TRN-101 per-port proxy mode:

1. Set `GA_PORTAL_ENABLED=true` in `ghostship.conf`
2. Re-run `install.sh` — `ga-portal` is added to the compose stack and takes over the dashboard ports
3. If `GA_PORTAL_TLS_MODE=internal` (default): run `caddy trust` once to trust the CA
4. Existing crews that had dashboard ports will need to be nuked and re-launched so Portside registers them at their new HTTPS URLs

For fresh installs, simply set `GA_PORTAL_ENABLED=true` before running `install.sh`.

## Limitations

- **Port exhaustion** — if all 50 ports are allocated, `launch` returns an error. Increase `GA_DASHBOARD_PORT_RANGE_SIZE` if you need more concurrent crew UIs.
- **Port collisions** — if the chosen range conflicts with other services on your host, change `GA_DASHBOARD_PORT_RANGE_START` in your config.
