## Why

The crew UI proxy works for the initial page load but breaks for SPA navigation: the KiroCrew gateway UI uses root-absolute paths for both static assets and client-side routing (e.g. navigates to `/chat`). When loaded via `/crews/{id}/ui/`, the browser resolves these paths against the transport host, not the crew gateway, so assets 404 and the page URL detaches from the crew context. The Python-layer catch-all approach (attempted in TRN-80 phase 1) fixed asset loading but cannot fix client-side navigation, which rewrites `window.location` to a root-absolute URL that Referer-based routing can't recover. The correct fix is at the web server layer. Found by Steve Mactaggart (stevemac007) in PR #3.

## What Changes

- The transport's Caddy instance gains a dynamic routing layer: when a crew is launched, the transport registers a per-crew reverse proxy block in Caddy via the admin API; when a crew is nuked, that block is removed.
- Each crew's UI is served at `http(s)://<host>/crews/{id}/ui/` with path prefix stripping — the SPA sees itself at the root of its upstream, so asset paths and client-side navigation work correctly.
- The `ohnomer/servers` Caddy deploy config is updated to enable the admin API on localhost and mount a writable config dir for the dynamic route file.
- `KIROCREW_CORS_ORIGINS` is injected with the transport's public origin at crew container create time (carried over from phase 1 — still needed so the SPA's API calls from the transport origin aren't CORS-rejected).
- **BREAKING:** The existing Python `_handle_crew_ui_proxy` and catch-all routes are removed. Crew UI is served exclusively via Caddy.

## Capabilities

### New Capabilities

- `crew-ui-spa-routing`: Full SPA support for crew UI — assets, client-side navigation, and WebSockets routed correctly via Caddy dynamic proxy.

### Modified Capabilities

- `proxy-hosting`: Crew UI proxy requirement updated to describe Caddy-layer routing; CORS injection requirement retained.
- `crew-lifecycle`: `launch` and `nuke` gain Caddy route registration and removal as part of their lifecycle.

## Impact

- `transport/server.py` — `launch` calls Caddy admin API to register crew UI route; `nuke` removes it; `_handle_crew_ui_proxy` and SPA catch-all removed.
- `transport/config.py` — new `GA_CADDY_ADMIN_URL` env var (default `http://localhost:2019`); `GA_CADDY_UI_ENABLED` flag (default `true`); graceful degradation when Caddy admin is unreachable.
- `ohnomer/servers/hyperv/academy/install.sh` — enable Caddy admin API on `localhost:2019`; make Caddy config dir writable (remove `:ro` mount).
- No MCP tool interface changes. `launch` and `nuke` behavior is unchanged from the Admiral's perspective.
