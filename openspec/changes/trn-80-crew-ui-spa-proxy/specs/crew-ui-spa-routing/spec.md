# crew-ui-spa-routing Specification

## Purpose

Enable the KiroCrew gateway SPA to load and navigate correctly when accessed via the transport's public URL, by routing crew UI traffic through a shared Caddy reverse proxy with path-prefix stripping.

## Requirements

### Requirement: Crew UI routed via Caddy with path stripping

The transport SHALL register a reverse-proxy route in Caddy at crew launch time. The route SHALL match `GET` and `POST` requests under `/crews/{crew_id}/ui/` and strip the `/crews/{crew_id}/ui` prefix before forwarding to `http://gs-{crew_id}:5476/`. WebSocket upgrade requests SHALL be forwarded transparently.

#### Scenario: SPA assets load correctly
- **WHEN** a browser loads `/crews/my-crew/ui/` and the SPA subsequently fetches `/assets/app.js`
- **THEN** Caddy routes `/assets/app.js` to `http://gs-my-crew:5476/assets/app.js` without any involvement from the transport Python layer

#### Scenario: Client-side navigation — asset requests continue to work
- **WHEN** the SPA navigates client-side (e.g. to `/chat`) while the browser tab still holds the session cookie set at initial load
- **THEN** subsequent asset fetches issued from that page are routed to the originating crew via the Caddy catch-all (see below)

#### Scenario: Client-side navigation — hard reload loses crew context
- **WHEN** a user hard-reloads the browser after the SPA has navigated to `/chat`
- **THEN** the transport serves a 404 for `/chat` (no crew context without the cookie); the user must navigate back to `/crews/{id}/ui/` to restore context
- **NOTE** Full navigation support (hard-reload surviving at `/chat`) requires subdomain-per-crew routing, which is out of scope for this change

#### Scenario: Caddy route registered at launch
- **WHEN** `launch` is called for crew `my-crew`
- **THEN** a Caddy route for `/crews/my-crew/ui/` is registered via the admin API before `launch` returns

#### Scenario: Caddy route removed at nuke
- **WHEN** `nuke` is called for crew `my-crew`
- **THEN** the Caddy route for `/crews/my-crew/ui/` is removed via the admin API

#### Scenario: Launch succeeds even if Caddy admin is unreachable
- **WHEN** `launch` is called and the Caddy admin API is unreachable
- **THEN** the crew is launched normally and a warning is logged; the UI via Caddy is unavailable but all MCP tools work

### Requirement: Routes reconciled on transport startup

On startup, the transport SHALL re-register any crew UI routes that have a corresponding route file in the data dir and a live crew in the registry. Routes for crews no longer in the registry SHALL be removed from Caddy and their route files deleted.

#### Scenario: Transport restart re-registers live crew routes
- **WHEN** the transport restarts with live crews that have route files
- **THEN** all live crew UI routes are re-registered with Caddy on startup

#### Scenario: Stale route files are cleaned up on startup
- **WHEN** a route file exists for a crew that is no longer in the registry
- **THEN** the transport removes the route from Caddy and deletes the route file

### Requirement: GA_CADDY_UI_ENABLED flag

When `GA_CADDY_UI_ENABLED=false`, the transport SHALL skip all Caddy route management and fall back to the existing Python-layer `_handle_crew_ui_proxy`. Default is `true`.
