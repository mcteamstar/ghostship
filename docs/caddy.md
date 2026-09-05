# Caddy Reverse Proxy (TRN-92)

Ghostship runs a Caddy container (`ga-portal`) as its TLS terminator, edge auth gate, and dashboard port router. As of TRN-103 it is a **required** component — `install.sh` always starts it; there is no opt-out.

> ⚠️ **Breaking change (TRN-103).** `GA_PORTAL_ENABLED` was removed. Caddy binds the dashboard port range (`64058–64107` by default); the transport does not bind those ports. Any deployment that previously set `GA_PORTAL_ENABLED=false` must re-run `install.sh`. See [Migration](#migration).

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
                  │    /dashboard-auth ────────────────▶ ga-transport     │
                  │    /login-ui      ────────────────▶ ga-transport     │
                  │    /dashboard-login ───────────────▶ ga-transport     │
                  │                                                       │
                  │  PER-CREW DASHBOARD SERVERS (dynamic, one per port):  │
                  │    :64058 (TLS)  forward_auth ──▶ ga-transport        │
                  │                 then proxy    ──▶ ga-transport:8000   │
                  │                             /crews/alpha/ui/{path}    │
                  │    :64059 (TLS)  forward_auth ──▶ ga-transport        │
                  │                 then proxy    ──▶ ga-transport:8000   │
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
2. **Per-crew dashboard ports (64058–64107)** — one Caddy server per allocated port, added/removed live via the Caddy admin API when crews launch/nuke. Each server has TLS + `forward_auth` + `reverse_proxy` to the crew gateway. No Caddy restart is needed.

### Single-port routing model

Each crew UI gets its own origin (`host:PORT/`) rather than a path prefix. This is a hard requirement: the KiroCrew SPA relies on being at the root origin for `history.pushState` navigation, hard reloads, and link sharing. Subdomain-per-crew and path-prefix routing both break the SPA. Caddy binds the entire dashboard port range and creates one server object per port as crews are launched.

## TLS modes

Set `GA_PORTAL_TLS_MODE` to one of:

| Mode | When to use | Notes |
|:-----|:------------|:------|
| `internal` (default) | Local dev, homelab, Tailscale networks | Caddy's built-in CA issues self-signed certs. Works on any hostname — localhost, private IPs, Tailscale `.ts.net` addresses. Requires a one-time `caddy trust` step to install the Caddy root CA into your host/browser trust store. The cert path is printed by `install.sh` and shown by `ghostship status`. |
| `tailscale` | Tailscale-connected deployments (recommended for vm23/academy) | Caddy provisions real browser-trusted certs for `.ts.net` hostnames via Tailscale's ACME endpoint. Requires the Tailscale daemon running on the host. No trust step — browsers accept the certs without any setup. Set `GA_PORTAL_DOMAIN` to your `.ts.net` hostname. |
| `acme` | Internet-facing deployments with public DNS | Standard Let's Encrypt / public ACME. Requires `GA_PORTAL_DOMAIN` set to a real DNS name and ports 80/443 reachable from the internet for ACME challenges. |
| `off` | Local dev, or when an upstream terminator already handles TLS | Plain HTTP on all ports. Useful when running behind a load balancer that terminates TLS. |

TLS applies to every listener Caddy owns — the main port and every per-crew dashboard port. The crew containers themselves are never exposed externally.

### Internal CA trust step (one-time)

When `GA_PORTAL_TLS_MODE=internal`, add the Caddy root CA to your trust store once. `install.sh` prints the path:

```
[CADDY] Internal CA root cert: /path/to/ga-portal-data/_data/caddy/pki/authorities/local/root.crt
[CADDY] Run once: caddy trust --ca /path/to/root.crt
```

`ghostship status` also surfaces the path so you can find it later. After trusting the CA, every per-crew cert Caddy issues is trusted automatically — you do not need to re-run this step for new crews.

## Dashboard auth flow (`forward_auth`)

The default auth mechanism for dashboard ports uses Caddy's `forward_auth` handler:

```
Browser ──GET :64058/──▶ ga-portal
                            │
                            ├─ forward_auth ──GET /dashboard-auth──▶ ga-transport
                            │                    │ valid gs_session cookie?
                            │                    ├─ YES → 200 + X-Crew-Cookie
                            │                    └─ NO  → 401 → Caddy redirects to /login-ui
                            │
                            └─ (on 200) reverse_proxy ──▶ ga-transport:8000
                                        rewrite /crews/alpha/ui/{path}
                                        passes X-Crew-Cookie as cookie header
```

1. Every request to a dashboard port hits Caddy's `forward_auth` check first.
2. Caddy calls `GET /dashboard-auth` on the transport, passing the request's cookies.
3. The transport validates the `gs_session` cookie (issued at `/dashboard-login`) and returns 200 or 401.
4. On 200, the transport also returns `X-Crew-Cookie: mc_token_5476=<value>`. Caddy's `copy_headers` carries this into the upstream request to the crew gateway, injecting the session cookie.
5. On 401, Caddy redirects the browser to `/login-ui`, which serves an HTML login form. Submitting the form POSTs to `/dashboard-login` with the operator API key (`GA_API_KEY`). A valid key issues a `gs_session` cookie and the browser retries.

`gs_session` cookies have a configurable TTL (`GA_PORTAL_SESSION_TTL_SECS`, default 24 h). Sessions are held in-memory and reset on transport restart.

No Caddy plugin is required for this flow. The vanilla `caddy:2` image is sufficient.

## MCP and file-transfer auth at the edge

When `GA_API_KEY` is set and Caddy is enabled, the `/mcp*` and `/files/*` routes on the main server require `Authorization: Bearer <GA_API_KEY>`. Requests without the correct token are rejected by Caddy with 401 before they reach the transport process:

```
Client ──/mcp──▶ ga-portal
                    │
                    ├─ Authorization: Bearer <correct> ──▶ ga-transport (proxied)
                    └─ missing / wrong Bearer           ──▶ 401 WWW-Authenticate: Bearer
```

The transport's own `BearerAuthMiddleware` remains active for defence-in-depth — it still runs, so a direct connection to `ga-transport` on `ga-starboard` is still checked.

## Quickstart

1. Add to your `ghostship.conf` (or `config/ghostship.conf.example`):

   ```bash
   GA_PORTAL_TLS_MODE=internal       # or tailscale / acme / off
   GA_PORTAL_DOMAIN=                 # required for tailscale and acme
   ```

2. Re-run `install.sh`:

   ```bash
   ./install.sh --config config/ghostship.conf
   ```

3. For `internal` mode: trust the Caddy root CA (path printed by step 2):

   ```bash
   caddy trust --ca /path/to/ga-portal-data/_data/caddy/pki/authorities/local/root.crt
   ```

   Or import the cert into your browser's trust store manually.

4. Crew dashboard URLs are now HTTPS: `https://host:64058/`.

## Auth upgrade paths

The `forward_auth`-based login gate in this change uses `GA_API_KEY` as the shared credential — exactly what operators already use today. For deployments that need stronger or more flexible auth, Caddy makes these upgrades **config-only changes** — no transport code involved.

### Caddy `basicauth`

Caddy handles HTTP Basic Auth natively against a bcrypt-hashed password. No session store, no transport changes, no plugin. Credentials are sent on every request (acceptable for ops tooling; less friendly for a browser SPA).

To switch a per-crew server from `forward_auth` to `basicauth`, replace the `forward_auth` handler in the server JSON with:

```json
{
  "handler": "authentication",
  "providers": {
    "http_basic": {
      "hash": {"algorithm": "bcrypt"},
      "accounts": [{"username": "admin", "password": "<bcrypt-hash>"}]
    }
  }
}
```

The transport does not need to change.

### `caddy-security` plugin (SSO / OIDC / OAuth2)

For full SSO — Google, GitHub, Tailscale identity, Authentik, Okta, or any OIDC provider — build a custom Caddy image with the [`caddy-security`](https://github.com/greenpau/caddy-security) plugin via [`xcaddy`](https://github.com/caddyserver/xcaddy):

```dockerfile
FROM caddy:2-builder AS builder
RUN xcaddy build --with github.com/greenpau/caddy-security

FROM caddy:2
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
```

Replace the `caddy:2` image reference in `compose.yml` with your custom image. Then replace the per-crew server's `forward_auth` handler block with a `caddy-security` auth policy. The transport and crew containers require no changes.

This is the recommended path for production deployments where operator-managed accounts, MFA, or organisation SSO is required.

## vm23 note — retiring the host Caddy

`ga-portal` is the sole TLS terminator and takes over all inbound traffic on ports 443/80 and the dashboard port range. The pre-existing host-level Caddy on vm23 is no longer needed and should be stopped and removed to avoid port conflicts:

```bash
sudo systemctl stop caddy
sudo systemctl disable caddy
```

Run `./install.sh` to apply the new compose stack before stopping the host Caddy, so there is no gap in service.

## Migration

As of TRN-103, `ga-portal` is always installed and `GA_PORTAL_ENABLED` was removed. Deployments that previously ran with `GA_PORTAL_ENABLED=false` must re-run `install.sh` to adopt the portal:

1. Remove any `GA_PORTAL_ENABLED` line from your config (it is ignored). Set `GA_PORTAL_TLS_MODE` / `GA_PORTAL_DOMAIN` as needed.
2. On vm23: stop the pre-existing host Caddy (see above).
3. Run `./install.sh --config config/ghostship.conf`. The regenerated `compose.yml` binds the dashboard port range to `ga-portal`, not `ga-transport`.
4. For `internal` TLS: run `caddy trust` with the printed path.
5. Existing crews survive — the transport's `_reconcile_registry` re-registers their Caddy servers on startup.

There is no opt-out and no rollback to the pre-portal per-port uvicorn mode; that code path was removed.

## Configuration reference

See [configuration.md](configuration.md) for the full `GA_PORTAL_*` variable table.

| Variable | Default | Description |
|:---------|:--------|:------------|
| `GA_PORTAL_TLS_MODE` | `off` | `internal` / `tailscale` / `acme` / `off` |
| `GA_PORTAL_DOMAIN` | _(unset)_ | Hostname for `tailscale` and `acme` modes |
| `GA_PORTAL_PORT` | `64057` | Port Caddy listens on (HTTP or HTTPS, any port). |
| `GA_PORTAL_SESSION_TTL_SECS` | `86400` | Session cookie TTL (seconds) |
