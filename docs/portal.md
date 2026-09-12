# Portal (Caddy Reverse Proxy)

Ghostship runs a Caddy container (`ga-portal`) as its TLS terminator, edge auth gate, and dashboard port router. It is a required component — `install.sh` always starts it.

## How it works

Caddy sits in front of all traffic:

```
                  ┌──────────────────────────────────────────────────────┐
  External        │  ga-portal (caddy:2 image, ga-portside)                │
  traffic ──────▶ │                                                       │
                  │  MAIN SERVER  :443 / :80                              │
                  │    /mcp*         ── Bearer check ──▶ ga-transport     │
                  │    /files/*      ── Bearer check ──▶ ga-transport     │
                  │    /health       ──────────────────▶ ga-transport     │
                  │    /dashboard/auth ────────────────▶ ga-transport     │
                  │    /dashboard/login ───────────────▶ ga-transport     │
                  │    /dashboard/logout ──────────────▶ ga-transport     │
                  │                                                       │
                  │  PER-CREW DASHBOARD SERVERS (dynamic, one per port):  │
                  │    :64058 (TLS)  forward_auth ──▶ ga-transport        │
                  │                 then proxy    ──▶ ga-transport:64057  │
                  │                             /crews/alpha/ui/{path}    │
                  │    :64059 (TLS)  forward_auth ──▶ ga-transport        │
                  │                 then proxy    ──▶ ga-transport:64057  │
                  │                             /crews/beta/ui/{path}     │
                  └────────────────────┬─────────────────────────────────┘
                                       │ admin API :2019 (ga-portside only)
                    launch → PUT /id/crew-{id}   (add server on its port)
                    nuke   → DELETE /id/crew-{id}
                  ┌────────────────────▼─────────────────────────────────┐
                  │  ga-transport:64057 (Python/uvicorn)                  │
                  │  BearerAuthMiddleware (defence in depth)              │
                  │  Caddy admin API calls serialised inside _registry_lock│
                  └────────────────────┬─────────────────────────────────┘
                                       │ http://gs-{id}:5476 (ga-starboard)
                  ┌────────────────────▼─────────────────────────────────┐
                  │  gs-alpha:5476   gs-beta:5476   ...                  │
                  │  (crew containers, never exposed externally)          │
                  └──────────────────────────────────────────────────────┘
```

Two routing tiers:

1. **Main port (443/80)** — static server written at install time. Handles MCP, file-transfer, health, and all three auth/login endpoints.
2. **Per-crew dashboard ports (64058–65081)** — one Caddy server per allocated port, added/removed live via the Caddy admin API when crews launch/nuke. Each server has TLS + `forward_auth` + `reverse_proxy` to the crew gateway.

## Dashboard proxy

When a crew is launched with `dashboard=True`, the transport allocates a dedicated port from the configured range and registers it with Portal.

```
Browser → host:64058 (HTTPS, via ga-portal)
        → forward_auth check at ga-transport:{PORT}/dashboard/auth
        → (on valid gs_session cookie) reverse_proxy → ga-transport:{PORT}
              rewrite → /crews/{crew_id}/ui/{original_path}
        → transport injects Cookie: mc_token_5476=<crew_token>
        → gs-{crew_id}:5476
```

Key properties:

- **Portal owns all dashboard port bindings.** The transport does not bind these ports directly.
- **Caddy talks only to `ga-transport:64057`.** Both the MCP/file routes and the per-crew dashboard routes upstream to `ga-transport:64057`. Caddy has no network path to crew containers.
- **The transport injects the session cookie.** The `mc_token_5476` cookie is added by the transport's UI-proxy endpoint, from `ga-transport`'s own IP. The cookie is transparently re-minted when near expiry — sessions never see a "Session expired" prompt.
- **WebSocket connections are proxied.** Real-time chat/task streaming over WebSocket is upgraded and relayed through the same endpoint.
- **TLS on every port.** Caddy terminates HTTPS on the main port and on every per-crew dashboard port.
- **`gs_session` cookie gate.** When `GA_API_KEY` is set, every dashboard port requires a valid `gs_session` cookie issued by `/dashboard/login`.
- **SPA navigation works correctly.** The SPA owns a full origin, so `history.pushState` navigation, hard reloads, and link sharing all work.
- **CORS is pre-configured.** The UI port origin is added to `KIROCREW_CORS_ORIGINS` at container create time.

### The `dashboard_url`

`launch(dashboard=True)` returns a `dashboard_url`:

```json
{
  "crew_id": "my-crew",
  "dashboard_url": "https://academy.example.com:64058/",
  ...
}
```

A headless crew has `dashboard_url: null`.

### Managing dashboard allocation after launch

**`POST /crews/{crew_id}/dashboard`** — allocate a UI port, register with Portal, and store `dashboard_port` in the registry. Returns `{"dashboard_url": "..."}`. No-op if the crew already has a dashboard.

```bash
curl -sX POST http://localhost:64057/crews/my-crew/dashboard | jq
```

**`DELETE /crews/{crew_id}/dashboard`** — deregister from Portal, release the port, and clear `dashboard_port` from the registry. Returns `{"dashboard_url": null}`.

```bash
curl -sX DELETE http://localhost:64057/crews/my-crew/dashboard | jq
```

## TLS modes

Set `GA_PORTAL_TLS_MODE` to one of:

| Mode | When to use | Notes |
|:-----|:------------|:------|
| `internal` (default) | Local dev, homelab, Tailscale networks | Caddy's built-in CA issues self-signed certs. Requires a one-time `caddy trust` step. |
| `tailscale` | Tailscale-connected deployments | Caddy provisions real browser-trusted certs for `.ts.net` hostnames. Set `GA_PORTAL_DOMAIN` to your `.ts.net` hostname. |
| `acme` | Internet-facing deployments | Standard Let's Encrypt. Requires `GA_PORTAL_DOMAIN` and ports 80/443 reachable from the internet. |
| `off` | Local dev, or upstream TLS terminator | Plain HTTP on all ports. |

### Internal CA trust (one-time)

When `GA_PORTAL_TLS_MODE=internal`, trust the Caddy root CA once. `install.sh` prints the path:

```bash
caddy trust --ca /path/to/ga-portal-data/_data/caddy/pki/authorities/local/root.crt
```

`ghostship status` also shows the path. After trusting the CA, all subsequent crew certs are trusted automatically.

## Dashboard auth flow

```
Browser ──GET :64058/──▶ ga-portal
                            │
                            ├─ forward_auth ──GET /dashboard/auth──▶ ga-transport
                            │                    │ valid gs_session cookie?
                            │                    ├─ YES → 200 + X-Crew-Cookie
                            │                    └─ NO  → 401 → redirect to /dashboard/login
                            │
                            └─ (on 200) reverse_proxy ──▶ ga-transport:64057
                                        /crews/alpha/ui/{path}
```

`gs_session` cookies have a configurable TTL (`GA_PORTAL_SESSION_TTL_SECS`, default 24 h). Sessions are held in-memory and reset on transport restart.

## MCP and file-transfer auth at the edge

When `GA_API_KEY` is set, the `/mcp*` and `/files/*` routes require `Authorization: Bearer <GA_API_KEY>`. Requests without the correct token are rejected by Caddy before reaching the transport.

## Setup

Portal is installed automatically by `install.sh`. Set the TLS mode in your config:

```bash
# ghostship.conf
GA_PORTAL_TLS_MODE=internal   # or tailscale / acme / off
```

```bash
./install.sh --config ./ghostship.conf
```

## Auth upgrade paths

The `forward_auth` gate uses `GA_API_KEY` as the shared credential. For stronger auth, Caddy supports config-only upgrades — no transport changes needed.

### Caddy `basicauth`

Replace the `forward_auth` handler in the server JSON with a `basicauth` block. Credentials are sent on every request (acceptable for ops tooling).

### `caddy-security` plugin (SSO / OIDC)

Build a custom Caddy image with [`caddy-security`](https://github.com/greenpau/caddy-security) via [`xcaddy`](https://github.com/caddyserver/xcaddy):

```dockerfile
FROM caddy:2-builder AS builder
RUN xcaddy build --with github.com/greenpau/caddy-security

FROM caddy:2
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
```

Replace the `forward_auth` block with a `caddy-security` auth policy. Recommended for production deployments requiring organisation SSO.

## Network topology

`ga-starboard` is reserved for transport ↔ crew container traffic:

- `ga-transport` is on `ga-starboard` (to reach `gs-*`) **and** `ga-portside` (so `ga-portal` can dial it).
- `ga-portal` is on `ga-portside` only — no route to crew containers.

## Firewall

The UI port range must be reachable from your browser:

```bash
sudo ufw allow 64058:65081/tcp
```

`install.sh` adds this rule automatically.

## Port persistence across restarts

Allocated ports are stored in `crews.json`. On transport restart, all crew ports are re-registered with Caddy, so existing dashboard URLs continue to work without re-launching crews.

## Configuration

| Variable | Default | Description |
|:---------|:--------|:------------|
| `GA_PORTAL_TLS_MODE` | `off` | `internal` / `tailscale` / `acme` / `off` |
| `GA_PORTAL_DOMAIN` | _(unset)_ | Hostname for `tailscale` and `acme` modes |
| `PORT` | `64057` | Port Caddy listens on |
| `GA_PORTAL_SESSION_TTL_SECS` | `86400` | Session cookie TTL (seconds) |
| `GA_DASHBOARD_PORT_RANGE_START` | `64058` | First port in the UI port range (1024 ports allocated) |

See [configuration.md](configuration.md) for the full variable reference.

> **Route reference:** For the authoritative list of all transport HTTP routes, fetch `GET /openapi.json` (no auth required) from the running transport.
