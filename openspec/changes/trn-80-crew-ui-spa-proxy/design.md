## Context

See proposal.md — Why for motivation.

The KiroCrew gateway UI is a React SPA designed to run at the root of an origin. Any path-prefix approach (`/crews/{id}/ui/`) breaks `window.history.pushState` navigation — once the SPA routes to `/chat`, the browser URL detaches from the crew context and hard reloads fail. Subdomain-per-crew requires wildcard DNS and TLS cert infrastructure. Port-per-crew requires only a port range allocation and a firewall rule — simpler to set up and simpler to maintain.

Crew containers already run with an internal gateway on port 5476 accessible only within the Podman network. Binding a host port to that internal port exposes the SPA at `http://<host>:<port>/` — a fully independent origin.

## Goals / Non-Goals

**Goals:**
- SPA assets, client-side navigation, and WebSockets all work correctly.
- Hard reloads and link sharing work (URL is stable across navigation).
- No DNS or TLS changes required.
- Ports allocated and released automatically at launch/nuke.

**Non-Goals:**
- TLS per-crew port (crews share no TLS on their UI ports — this is an internal/Tailscale deployment).
- Supporting more concurrent crews than `GA_UI_PORT_RANGE_SIZE` allows.

## Decisions

**D1: Port allocation from a configurable range stored in crews.json**

A module-level set `_ui_ports_in_use` is populated from `crews.json` at startup. At launch, the transport scans `GA_UI_PORT_RANGE_START` to `GA_UI_PORT_RANGE_START + GA_UI_PORT_RANGE_SIZE - 1` for the first port not in `_ui_ports_in_use`, binds it, and writes it to the crew's `crews.json` entry as `ui_port`. At nuke, the port is removed from `_ui_ports_in_use` and the entry is cleared.

Defaults: `GA_UI_PORT_RANGE_START=9000`, `GA_UI_PORT_RANGE_SIZE=50` (ports 9000–9049).

Alternatives considered:
- *Dynamic OS port allocation*: simpler but gives non-deterministic ports that change on restart. Stable ports per crew are preferable so bookmarks and shared URLs survive a transport restart.
- *Caddy dynamic proxy with path stripping*: fixes assets but not hard-reload navigation. Dropped in favour of port-per-crew.
- *Subdomain per crew*: correct, but requires wildcard DNS + TLS. Port-per-crew achieves the same origin isolation with only a firewall rule.

**D2: Port bound via podman run -p flag**

The existing `podman.container_create` call accepts an optional `ports` parameter (`{host_port: container_port}`). Pass `{ui_port: 5476}` at crew create time. This is the only transport-side change needed for binding — no Caddy involvement.

**D3: ui_url returned in launch response**

`launch` returns `ui_url: f"http://{GA_HOST_URL or 'localhost'}:{ui_port}/"` so the Admiral gets the direct link without having to compute it. The `crews` list also includes `ui_url` per crew.

**D4: CORS injection at container create**

`KIROCREW_CORS_ORIGINS` is injected with the transport's public origin at `container_create` time so the SPA's API calls (to the crew gateway) aren't CORS-rejected when the browser is on the UI port origin. The crew gateway's own internal origin is preserved.

**D5: GA_CADDY_UI_ENABLED=false preserves Python proxy as fallback**

For installs that haven't opened the port range, set `GA_UI_PORT_ENABLED=false` (default `true`) to skip port allocation entirely and fall back to the existing `_handle_crew_ui_proxy`. Named `GA_UI_PORT_ENABLED` rather than `GA_CADDY_UI_ENABLED` since Caddy is no longer involved.

## Risks / Trade-offs

- **Port exhaustion** → If all ports in the range are allocated, `launch` returns an error. The default range (50 ports) is generous for typical use. Document clearly.
- **Port collision with other services** → The chosen range (9000–9049) should be checked against existing vm23 services before deploying. `GA_UI_PORT_RANGE_START` is configurable to avoid conflicts.
- **Firewall configuration is manual** → The `ohnomer/servers` deploy script should open the port range in `ufw` automatically, or document the Tailscale ACL addition. This is a one-time setup step.
- **Stopped crew port still bound** → When a crew is stopped (idle), its host port binding is removed by Podman. On restart via `_ensure_crew_running`, the port must be re-bound. The `podman.container_start` call does not re-apply port bindings from `container_create` — port bindings are set at create time and persist across stop/start. Verify this behaviour; if not, the port binding approach needs adjustment.

## Migration Plan

1. Add `ufw allow 9000:9049/tcp` (or Tailscale ACL equivalent) on vm23.
2. Deploy updated transport.
3. Existing live crews have no `ui_port` — they need to be nuked and re-launched to get a port assignment.
4. Rollback: set `GA_UI_PORT_ENABLED=false` — reverts to Python proxy without redeploying.
