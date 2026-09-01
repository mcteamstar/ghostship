## Why

The crew UI proxy works for the initial page load but breaks for SPA navigation: the KiroCrew gateway UI uses root-absolute paths for both static assets and client-side routing (e.g. navigates to `/chat`). Any approach that serves the SPA under a path prefix (`/crews/{id}/ui/`) cannot fix `window.history.pushState` calls that rewrite the browser URL to a root-absolute path — hard reloads and link sharing break. The correct fix is to give each crew's UI its own origin. Found by Steve Mactaggart (stevemac007) in PR #3.

## What Changes

- Each crew is assigned a dedicated host port from a configurable range (`GA_UI_PORT_RANGE_START`, default 9000) at launch time. The port is bound to the crew's internal gateway port (5476) via `podman run -p <host_port>:5476`.
- The crew's assigned UI port is stored in `crews.json` and returned in the `launch` response as `ui_url`.
- At nuke, the port is released back to the pool.
- `KIROCREW_CORS_ORIGINS` is injected with the transport's public origin at crew container create time, so the SPA's API calls from the UI port aren't CORS-rejected by the crew gateway.
- The existing Python `_handle_crew_ui_proxy` routes are removed from the default code path (retained behind `GA_CADDY_UI_ENABLED=false` for backwards compatibility during transition).

## Capabilities

### New Capabilities

- `crew-ui-spa-routing`: Each crew's UI is served at its own host port. The SPA owns its entire origin — assets, client-side navigation, and WebSockets all work without path-prefix complications.

### Modified Capabilities

- `crew-lifecycle`: `launch` allocates a UI port and returns `ui_url`; `nuke` releases it.
- `proxy-hosting`: CORS injection requirement retained; Python UI proxy requirement updated to reflect port-based approach.

## Impact

- `transport/server.py` — `launch` allocates a port from the pool and passes `-p <port>:5476` to `container_create`; `nuke` releases it; `_handle_crew_ui_proxy` removed from default path.
- `transport/config.py` — new `GA_UI_PORT_RANGE_START` (default 9000) and `GA_UI_PORT_RANGE_SIZE` (default 50) env vars.
- `crews.json` — new `ui_port` field per crew entry.
- `ohnomer/servers/hyperv/academy/install.sh` — open the UI port range in `ufw` (or document for Tailscale ACL).
- No MCP tool interface breaking changes. `launch` response gains `ui_url`.
