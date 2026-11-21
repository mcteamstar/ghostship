# transport/dashboard/auth Specification

## Purpose

Provides a cookie-gated login flow that Caddy enforces via `forward_auth` before proxying browser requests to any crew dashboard port, so dashboards are not reachable from unauthenticated browsers even when the port is network-accessible. Closes the TRN-91 gap.

## Requirements

### Requirement: verify_password handles scrypt resource exceptions

`verify_password()` SHALL return `False` (and not raise) when the scrypt hash
verification raises `OSError` (maxmem exceeded) or `OverflowError` (parameter
overflow). These exceptions join the existing `(ValueError, TypeError)` in the
catch clause.

#### Scenario: Extreme scrypt parameters return False, not exception
- **WHEN** a stored hash has extreme `n`/`r`/`p` values that exceed system scrypt limits
- **THEN** `verify_password()` returns `False`
- **THEN** no exception propagates to the caller

### Requirement: forward_auth is the dashboard auth mechanism

Each per-crew Caddy dashboard server SHALL gate requests with `forward_auth` to `GET /dashboard/auth`: 200 proxies and 401 redirects to `/dashboard/login`. This needs no plugin; basicauth or OIDC alternatives require only a Caddy-config change.

#### Scenario: forward_auth gates every dashboard request
- **WHEN** a browser requests a crew dashboard port
- **THEN** Caddy first issues `GET /dashboard/auth` to the transport with the browser's cookies
- **THEN** the crew gateway is reached only if that check returns 200

### Requirement: Forward-auth endpoint validates the session cookie and returns the crew cookie
The transport SHALL expose `GET /dashboard/auth` that reads the `gs_session` cookie, and returns 200 if the token is valid and unexpired or 401 otherwise. On 200 it SHALL include an `X-Crew-Cookie` response header carrying the target crew's `mc_token_5476` session cookie value, which Caddy copies into the upstream request so the crew gateway authenticates the browser automatically. The target crew SHALL be identified from the incoming dashboard port (mapped to a crew via the registry).

#### Scenario: Valid session cookie allows dashboard access and injects crew cookie
- **WHEN** a browser sends a request to crew `alpha`'s dashboard port with a valid `gs_session` cookie
- **THEN** Caddy's `forward_auth` call to `GET /dashboard/auth` returns 200 with `X-Crew-Cookie: mc_token_5476=<alpha's cookie>`
- **THEN** Caddy proxies the request to `gs-alpha:5476` with that cookie injected

#### Scenario: Missing or expired session cookie is denied
- **WHEN** a browser sends a request without a valid `gs_session` cookie
- **THEN** `GET /dashboard/auth` returns 401
- **THEN** Caddy redirects the browser to `/dashboard/login`

### Requirement: MCP/API auth posture

Caddy SHALL be the first auth gate for all traffic — Bearer enforcement for MCP/files at the edge and `forward_auth` for dashboards. `BearerAuthMiddleware` SHALL remain active as defence in depth for requests that reach the transport directly over `ga-portside` or `ga-starboard`.

#### Scenario: Caddy is the first gate for all traffic

- **WHEN** `GA_API_KEY` is set
- **THEN** an unauthenticated MCP or dashboard request is rejected by Caddy before reaching the transport
- **THEN** the transport's `BearerAuthMiddleware` still runs for requests that reach it directly over `ga-portside` or `ga-starboard`
