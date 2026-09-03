## Purpose

Provides a cookie-gated login page that issues a session cookie checked by Caddy before proxying browser requests to crew dashboard UIs, so dashboards are not reachable from unauthenticated browsers even when ports are network-accessible.

## ADDED Requirements

### Requirement: Transport login endpoint issues session cookie
The transport SHALL expose `POST /dashboard-login` that accepts a `ga_api_key` body field, validates it against `GA_API_KEY` using constant-time comparison, and — on success — returns a `Set-Cookie: gs_session=<token>; HttpOnly; SameSite=Lax; Path=/` header with a cryptographically random 32-byte hex token. The token SHALL be recorded in a short-lived in-memory store (TTL configurable, default 24 h). On validation failure the endpoint SHALL return 401.

#### Scenario: Valid API key returns session cookie
- **WHEN** `POST /dashboard-login` is sent with a correct `ga_api_key`
- **THEN** the response is 200 with a `Set-Cookie: gs_session=<token>` header
- **THEN** the token is stored for future forward-auth checks

#### Scenario: Invalid API key returns 401
- **WHEN** `POST /dashboard-login` is sent with an incorrect `ga_api_key`
- **THEN** the response is 401 with no Set-Cookie header

### Requirement: Forward-auth endpoint validates session cookie
The transport SHALL expose `GET /dashboard-auth` that reads the `gs_session` cookie from the request and returns 200 if the token is valid and unexpired, or 401 otherwise. Caddy SHALL be configured to call this endpoint as a `forward_auth` check before proxying any `/crews/{id}/ui/` request.

#### Scenario: Valid session cookie allows dashboard access
- **WHEN** a browser sends a request to `/crews/alpha/ui/` with a valid `gs_session` cookie
- **THEN** Caddy calls `GET /dashboard-auth` on the transport
- **THEN** transport returns 200
- **THEN** Caddy proxies the request to `gs-alpha:5476`

#### Scenario: Missing or expired session cookie redirects to login
- **WHEN** a browser sends a request to `/crews/alpha/ui/` without a valid `gs_session` cookie
- **THEN** Caddy calls `GET /dashboard-auth`
- **THEN** transport returns 401
- **THEN** Caddy returns a redirect to `/login-ui` or a 401 (configurable)

### Requirement: Login UI served by transport
The transport SHALL serve a minimal HTML login page at `GET /login-ui` that submits to `POST /dashboard-login`. The page SHALL be served without authentication. After a successful login submission the browser SHALL be redirected to the originally requested URL (preserved in a `next` query parameter).

#### Scenario: Unauthenticated browser is shown login page
- **WHEN** a browser navigates to `/crews/alpha/ui/` with no session cookie
- **THEN** the browser eventually lands on `/login-ui?next=/crews/alpha/ui/`
- **THEN** the response is a valid HTML page with a password form

### Requirement: Forward-auth bypassed when Caddy is disabled
When `GA_CADDY_ENABLED=false`, the `/dashboard-auth` and `/login-ui` endpoints SHALL still be served (they are inert without Caddy using them), but the per-port proxy servers SHALL NOT enforce the cookie check — the existing `GA_API_KEY` bearer auth remains the sole mechanism.

#### Scenario: Forward-auth endpoints exist without Caddy
- **WHEN** the transport starts with `GA_CADDY_ENABLED=false`
- **THEN** `GET /dashboard-auth` and `GET /login-ui` return valid responses
- **THEN** per-port proxy auth behavior is unchanged
