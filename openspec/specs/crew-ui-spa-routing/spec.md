# crew-ui-spa-routing Specification

## Purpose

Enable SPAs served by the KiroCrew crew gateway to load correctly through the transport UI proxy. Root-absolute asset requests issued by the browser after the initial page load must be resolved back to the originating crew and proxied transparently, without any change to SPA source code.

## Requirements

### Requirement: Root-absolute SPA asset requests are re-routed to the originating crew

The transport SHALL intercept `GET` requests for root-absolute paths that do not match any existing transport route (MCP, files, login, crews API) when those requests carry a `Referer` header whose path begins with `/crews/{crew_id}/ui/`. The transport SHALL proxy such requests to `http://gs-{crew_id}:5476/{path}` on the originating crew's gateway, following the same forwarding rules as the existing UI proxy.

#### Scenario: SPA script fetch after initial page load (Referer present)
- **WHEN** a browser that loaded `/crews/my-crew/ui/` subsequently fetches `/static/app.js`
- **AND** the request carries `Referer: http://transport-host/crews/my-crew/ui/`
- **THEN** the transport proxies `GET http://gs-my-crew:5476/static/app.js` and streams the response back with the original status and headers

#### Scenario: Unrecognised root path with no matching crew Referer passes through
- **WHEN** a `GET /static/app.js` request carries no `Referer` header (or a `Referer` that does not match `/crews/{id}/ui/`)
- **AND** no `crew_ui_context` cookie is present
- **THEN** the transport returns HTTP 404 with a message indicating no crew context

#### Scenario: Transport route takes priority over SPA re-routing
- **WHEN** a request path matches an existing transport route (e.g. `/mcp`, `/files/**`, `/login`)
- **THEN** the transport routes it normally and the SPA catch-all is NOT invoked

### Requirement: crew_ui_context cookie set on initial UI proxy response

The transport SHALL set a `crew_ui_context` cookie containing the `crew_id` on every response it streams back from the initial `/crews/{crew_id}/ui` or `/crews/{crew_id}/ui/` request. The cookie SHALL be `HttpOnly`, `SameSite=Strict`, scoped to `/`, and have a short TTL (≤ 1 hour).

#### Scenario: Cookie set on initial page load
- **WHEN** `GET /crews/my-crew/ui/` is requested
- **THEN** the response includes `Set-Cookie: crew_ui_context=my-crew; Path=/; HttpOnly; SameSite=strict; Max-Age=3600`

#### Scenario: Cookie used as fallback when Referer is absent
- **WHEN** a browser fetches `/static/app.js` with no `Referer` header
- **AND** the request carries `Cookie: crew_ui_context=my-crew`
- **THEN** the transport proxies the request to `http://gs-my-crew:5476/static/app.js`
