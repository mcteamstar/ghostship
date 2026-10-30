# Portal (Caddy Reverse Proxy)

Ghostship runs a Caddy container (`ga-portal`) as its TLS terminator, edge auth gate, and dashboard port router. It is a required component — `install.sh` always starts it.

## How it works

```
  External traffic
       │
  [ga-portal :443/:80]          (ga-portside network)
       │
       ├── /              ──── forward_auth ──▶ ga-radar (Radar dashboard)
       ├── /api/crews*    ──── forward_auth ──▶ ga-radar
       ├── /mcp*          ──── Bearer check ──▶ ga-transport
       ├── /files/*       ──── Bearer check ──▶ ga-transport
       ├── /health        ──────────────────▶ ga-transport
       ├── /dashboard/*   ──────────────────▶ ga-transport
       │
       └── :64058–64121   ──── forward_auth ──▶ ga-transport
                               (per-crew KC dashboards, added/removed live)
                                       │ (ga-starboard network)
                              [gs-alpha:5476]  [gs-beta:5476]  ...
```

Two routing tiers:

1. **Main port (443/80)** — static config written at install time. Covers MCP, files, health, auth, the Radar fleet dashboard (`/`), and the fleet API (`/api/crews`).
2. **Per-crew dashboard ports (64058–64121)** — one Caddy server per port, added/removed live via the Caddy admin API on `launch`/`nuke`.

## Radar fleet dashboard

`GET /` serves the Radar SPA — a browser view of all crews without requiring an MCP session. See [radar.md](radar.md) for full documentation.

Radar runs as its own container (`ga-radar`) on `ga-portside`. Caddy proxies `/` and `/api/crews*` to `ga-radar:8080`; Radar in turn calls `ga-transport`'s internal `/internal/crews` endpoint using the shared transport secret.

## Dashboard proxy (per-crew KC)

When a crew is launched with `dashboard=True`, the transport allocates a port from `GA_DASHBOARD_PORT_RANGE_START`–`GA_DASHBOARD_PORT_RANGE_SIZE` and registers it with Portal.

```
Browser → host:64058
        → forward_auth → /dashboard/auth (valid gs_session?)
        → reverse_proxy → ga-transport:64057/crews/{crew_id}/ui/{path}
        → transport injects mc_token_5476 cookie → gs-{crew_id}:5476
```

Key properties: Portal owns all port bindings. Caddy only talks to `ga-transport:64057` — it has no network path to crew containers. The transport injects and re-mints the crew session cookie. TLS on every port. WebSocket connections are proxied. SPA navigation works.

### Managing dashboard allocation after launch

```bash
# Allocate a port and register with Portal
curl -sX POST http://localhost:64057/crews/my-crew/dashboard | jq
# → {"dashboard_url": "https://..."}

# Release the port
curl -sX DELETE http://localhost:64057/crews/my-crew/dashboard | jq
# → {"dashboard_url": null}
```

## TLS modes

| Mode | When to use |
|:-----|:------------|
| `off` (default) | Local dev or upstream TLS terminator |
| `internal` | Local dev, homelab, Tailscale — Caddy's built-in CA. Requires one-time `caddy trust`. |
| `tailscale` | Tailscale deployments — real certs for `.ts.net` hostnames. Requires `GA_PORTAL_DOMAIN`. |
| `acme` | Internet-facing — Let's Encrypt. Requires `GA_PORTAL_DOMAIN` and ports 80/443 open. |

### Internal CA trust (one-time)

```bash
caddy trust --ca /path/to/ga-portal-data/_data/caddy/pki/authorities/local/root.crt
```

`install.sh` prints the path. After trusting once, all subsequent crew certs are trusted automatically.

## Auth

`gs_session` cookies are issued by `/dashboard/login` and validated by `/dashboard/auth`. TTL is `GA_PORTAL_SESSION_TTL_SECS` (default 24 h). Sessions are in-memory and reset on transport restart.

When `GA_API_KEY` is set, `/mcp*` and `/files/*` require `Authorization: Bearer <key>`. Caddy rejects invalid tokens before they reach the transport.

### Auth upgrade paths

Auth upgrade paths are outside ghostship's supported config. For SSO/OIDC, build a custom `ga-portal` image using [xcaddy](https://github.com/caddyserver/xcaddy) with [caddy-security](https://github.com/greenpau/caddy-security) plugin.

## Firewall

The UI port range must be open from your browser:

```bash
sudo ufw allow 64058:64121/tcp
```

`install.sh` adds this rule automatically.

## Configuration

| Variable | Default | Description |
|:---------|:--------|:------------|
| `GA_PORTAL_TLS_MODE` | `off` | `off` / `internal` / `tailscale` / `acme` |
| `GA_PORTAL_DOMAIN` | _(unset)_ | Hostname for `tailscale` / `acme` modes |
| `PORT` | `64057` | Port Caddy listens on |
| `GA_PORTAL_SESSION_TTL_SECS` | `86400` | `gs_session` cookie TTL (seconds) |
| `GA_DASHBOARD_PORT_RANGE_START` | `64058` | First port in the dashboard range |
| `GA_DASHBOARD_PORT_RANGE_SIZE` | `64` | Number of ports in the dashboard range |

See [configuration.md](configuration.md) for the full variable reference.

> **Route reference:** Fetch `GET /openapi.json` (no auth required) from the running transport for the authoritative list of all HTTP routes.
