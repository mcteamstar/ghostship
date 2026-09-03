## Why

The current transport serves plain HTTP over a single port (64057 for MCP + 50 ports for crew dashboards), has no TLS path, and relies on network-layer isolation alone to protect crew dashboard UIs. Three separate problems — no browser-friendly dashboard auth (TRN-91), no TLS, and an awkward port-per-crew model — converge on the same structural gap: there is no programmable reverse-proxy layer between the public network and the transport's internal routing. Bundling Caddy as an optional, auto-configured transport layer solves all three at once without requiring an external deployment dependency.

## What Changes

- **New `ga-caddy` container** added to the compose stack (opt-in via `GA_CADDY_ENABLED=true`).
- **Caddy admin API integration** in `transport/server.py`: crew registration (`launch`) and deregistration (`nuke`) each call the Caddy admin API to add/remove per-crew route blocks. No polling. No file writes. Zero-downtime reloads.
- **MCP and file-transfer routes** (`/mcp`, `/files/*`) are proxied through Caddy instead of being exposed directly, with GA_API_KEY forwarded via `forward_auth` or header pass-through.
- **Dashboard routing** collapses from 50 individual ports to path-prefix routing under a single port: `/crews/{id}/ui/` → `gs-{id}:5476`. The 50-port daemon-thread model in `server.py` is retained as a fallback when Caddy is disabled.
- **TLS**: Caddy auto-provisions certificates. For local installs: internal CA via `tls internal`. For remote/Tailscale: ACME via Let's Encrypt or ZeroSSL. Config selectable via `GA_CADDY_TLS_MODE=internal|acme|off`.
- **Cookie-gated login** for dashboard routes: Caddy checks for a `gs_session` cookie issued by the transport's `/login` endpoint before proxying to crew UIs, acting on TRN-91.
- **`install.sh` updated** to write a Caddy `initial-config.json` and add the `ga-caddy` service to the generated `compose.yml` when `GA_CADDY_ENABLED=true`.
- **`BearerAuthMiddleware`** is retained for defence-in-depth on MCP calls (Caddy adds a layer; the transport does not become fully trusting of network peers).
- **`GA_DASHBOARD_PORT_ENABLED`** defaults to `false` when Caddy is enabled, since per-port proxies are redundant with Caddy path routing.
- **Docs**: new `docs/caddy.md`, updates to `docs/dashboard-proxy.md`, `docs/auth.md`, `docs/configuration.md`.

## Capabilities

### New Capabilities

- `transport/caddy-proxy`: Caddy container lifecycle, initial JSON config generation, per-crew route registration and deregistration via the Caddy admin API (`POST /config/apps/http/servers/ga/routes`).
- `transport/dashboard-auth`: Cookie-gated login page that issues a `gs_session` cookie checked by Caddy before proxying to crew dashboards (TRN-91 surface, implemented here via Caddy `forward_auth`).
- `transport/tls`: Auto-provisioned TLS via Caddy (internal CA for local/dev, ACME for remote), replacing the manual `GA_TLS_CERTFILE/GA_TLS_KEYFILE` path.

### Modified Capabilities

- `transport/dashboard-proxy`: Path-prefix routing (`/crews/{id}/ui/`) replaces per-port daemon threads when Caddy is enabled. Per-port model retained as fallback.

## Impact

- `install.sh`: adds `GA_CADDY_ENABLED`, `GA_CADDY_TLS_MODE`, `GA_CADDY_DOMAIN` variables, writes `initial-config.json`, adds `ga-caddy` service to generated `compose.yml`.
- `transport/server.py`: adds `_caddy_register_crew` / `_caddy_deregister_crew` calls in `launch` / `nuke`; adds `_handle_login_cookie_post` for the `gs_session` cookie endpoint; suppresses per-port server start when `GA_CADDY_ENABLED=true`.
- `transport/Containerfile`: no change (Caddy runs as a separate container).
- `transport/config.py`: new fields `ga_caddy_enabled`, `ga_caddy_admin_url`, `ga_caddy_tls_mode`, `ga_caddy_domain`.
- Compose template: new `ga-caddy` service stanza, Caddy admin port internal-only.
- Docs: `docs/caddy.md` (new), `docs/dashboard-proxy.md`, `docs/auth.md`, `docs/configuration.md`.
- Existing deployments unaffected: `GA_CADDY_ENABLED` defaults to `false`.
