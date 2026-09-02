## Why

The crew UI proxy works for the initial page load but breaks for SPA navigation: the KiroCrew gateway UI uses root-absolute paths for both static assets and client-side routing (e.g. navigates to `/chat`). Any approach that serves the SPA under a path prefix (`/crews/{id}/ui/`) cannot fix `window.history.pushState` navigation. The correct fix is to give each crew's UI its own origin. Found by Steve Mactaggart (stevemac007) in PR #3.

## What Changes

- Each crew is assigned a dedicated port from a configurable range (`GA_UI_PORT_RANGE_START`, default 64058) at launch time.
- The transport (Python/uvicorn) binds an additional listener on the allocated port for the duration of the crew's life. All requests arriving on that port are reverse-proxied to `http://gs-{crew_id}:5476/` — the crew gateway.
- Because the transport handles all these ports, `GA_API_KEY` auth, rate limiting, and audit logging apply automatically. No Caddy involvement, no direct Podman port bindings to host, no open network surface beyond the transport's own ports.
- At nuke, the port listener is removed and the port returned to the pool.
- `KIROCREW_CORS_ORIGINS` is injected with the transport's public origin at crew container create time so the SPA's API calls aren't CORS-rejected.
- The `launch` response and `crews` list include `ui_url`.
- **Replaces** the previous approach (direct Podman port binding), which bypassed transport auth entirely.

## Capabilities

### New Capabilities

- `crew-ui-spa-routing`: Each crew's UI is served at its own port on the transport. The SPA owns its entire origin — assets, client-side navigation, and hard reloads all work. All traffic flows through the transport so security policies are uniformly enforced.

### Modified Capabilities

- `crew-lifecycle`: `launch` allocates a UI port and starts a transport listener; `nuke` removes it.
- `proxy-hosting`: CORS injection requirement retained; crew UI proxy updated to describe per-port transport listeners.

## Impact

- `transport/server.py` — port allocation helpers; `launch` starts a per-port uvicorn sub-application or asyncio server; `nuke` stops it; catch-all proxy handler routes by incoming port to the right crew.
- `transport/config.py` — `GA_UI_PORT_RANGE_START` (default 64058), `GA_UI_PORT_RANGE_SIZE` (default 50), `GA_UI_PORT_ENABLED` (default true).
- `transport/podman.py` — remove the `ports` parameter added in the previous approach (no Podman port binding needed).
- `scripts/install.sh` — expose the UI port range via `ufw` (or document for the operator); add env vars to compose template.
- No Caddy changes required.
- No MCP tool interface breaking changes. `launch` response gains `ui_url`.
