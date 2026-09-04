# transport/dashboard-auth Specification

## Purpose

Provides a cookie-gated login flow that Caddy enforces via `forward_auth` before proxying browser requests to any crew dashboard port, so dashboards are not reachable from unauthenticated browsers even when the port is network-accessible. Closes the TRN-91 gap.

## Requirements

### Requirement: forward_auth is the default dashboard auth mechanism
When `GA_PORTSIDE_ENABLED=true`, each per-crew Caddy dashboard server SHALL run a `forward_auth` handler that calls `GET /dashboard-auth` on the transport (main port) before proxying to the crew gateway. On a 200 response the request SHALL be proxied; on 401 the browser SHALL be redirected to `/login-ui`. This mechanism SHALL require no Caddy plugin. `basicauth` and the `caddy-security` OIDC/OAuth2 plugin SHALL be documented as supported alternatives that are activated by a Caddy-config change, not a transport code change.

#### Scenario: forward_auth gates every dashboard request
- **WHEN** a browser requests a crew dashboard port and Caddy is enabled
- **THEN** Caddy first issues `GET /dashboard-auth` to the transport with the browser's cookies
- **THEN** the crew gateway is reached only if that check returns 200

### Requirement: Transport login endpoint issues session cookie
The transport SHALL expose `POST /dashboard-login` that accepts a `ga_api_key` field, validates it against `GA_API_KEY` using constant-time comparison, and — on success — returns `Set-Cookie: gs_session=<token>; HttpOnly; SameSite=Lax; Secure; Path=/` with a cryptographically random 32-byte hex token recorded in a short-lived in-memory store (TTL configurable, default 24 h). On failure it SHALL return 401 with no cookie.

#### Scenario: Valid API key returns session cookie
- **WHEN** `POST /dashboard-login` is sent with a correct `ga_api_key`
- **THEN** the response is 200 with a `Set-Cookie: gs_session=<token>` header
- **THEN** the token is stored for future forward-auth checks

#### Scenario: Invalid API key returns 401
- **WHEN** `POST /dashboard-login` is sent with an incorrect `ga_api_key`
- **THEN** the response is 401 with no Set-Cookie header

### Requirement: Forward-auth endpoint validates the session cookie and returns the crew cookie
The transport SHALL expose `GET /dashboard-auth` that reads the `gs_session` cookie, and returns 200 if the token is valid and unexpired or 401 otherwise. On 200 it SHALL include an `X-Crew-Cookie` response header carrying the target crew's `mc_token_5476` session cookie value, which Caddy copies into the upstream request so the crew gateway authenticates the browser automatically. The target crew SHALL be identified from the incoming dashboard port (mapped to a crew via the registry).

#### Scenario: Valid session cookie allows dashboard access and injects crew cookie
- **WHEN** a browser sends a request to crew `alpha`'s dashboard port with a valid `gs_session` cookie
- **THEN** Caddy's `forward_auth` call to `GET /dashboard-auth` returns 200 with `X-Crew-Cookie: mc_token_5476=<alpha's cookie>`
- **THEN** Caddy proxies the request to `gs-alpha:5476` with that cookie injected

#### Scenario: Missing or expired session cookie is denied
- **WHEN** a browser sends a request without a valid `gs_session` cookie
- **THEN** `GET /dashboard-auth` returns 401
- **THEN** Caddy redirects the browser to `/login-ui`

### Requirement: Login UI served by transport
The transport SHALL serve a minimal HTML login page at `GET /login-ui` (no authentication required) that submits `ga_api_key` to `POST /dashboard-login`. After a successful login the browser SHALL be redirected to the originally requested URL, preserved in a `next` query parameter.

#### Scenario: Unauthenticated browser is shown login page
- **WHEN** a browser hits a crew dashboard port with no session cookie
- **THEN** it lands on `/login-ui?next=<original-url>`
- **THEN** the response is a valid HTML page with a password form

### Requirement: MCP/API auth posture with and without Caddy
When `GA_PORTSIDE_ENABLED=false`, MCP and file auth SHALL be `BearerAuthMiddleware` when `GA_API_KEY` is set, and dashboard ports SHALL be unauthenticated (status quo). When `GA_PORTSIDE_ENABLED=true`, Caddy SHALL be the first auth gate for all traffic — Bearer enforcement for MCP/files at the edge and `forward_auth` for dashboards — while `BearerAuthMiddleware` remains active as defence in depth.

#### Scenario: Caddy disabled preserves current posture
- **WHEN** `GA_PORTSIDE_ENABLED=false`
- **THEN** dashboard ports are unauthenticated and MCP auth is `BearerAuthMiddleware` when `GA_API_KEY` is set

#### Scenario: Caddy enabled makes Caddy the first gate
- **WHEN** `GA_PORTSIDE_ENABLED=true` and `GA_API_KEY` is set
- **THEN** an unauthenticated MCP or dashboard request is rejected by Caddy before reaching the transport
- **THEN** the transport's `BearerAuthMiddleware` still runs for requests that reach it directly over `ga-net`
