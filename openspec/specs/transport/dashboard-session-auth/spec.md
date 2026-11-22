# dashboard-session-auth Specification

## Purpose

Hardens the transport's dashboard login gate with brute-force throttling, a server-side revocable session store, an explicit logout endpoint, and a TLS-conditional `Secure` cookie flag.
## Requirements
### Requirement: Brute-force throttle on dashboard login
The transport SHALL apply a sliding-window failed-attempt throttle to `POST /dashboard/login`, keyed on the request's source IP, derived from the ASGI connection tuple rather than from `X-Forwarded-For`. When the number of failed attempts from a source within the configured window reaches the maximum, the endpoint SHALL return HTTP 429 without evaluating the submitted credential. A successful login SHALL reset the counter for that source.

#### Scenario: Excessive failed logins from one source are rejected
- **WHEN** `POST /dashboard/login` is called with an incorrect `ga_api_key` more than the configured maximum number of times within the throttle window from the same source IP
- **THEN** the transport returns HTTP 429 and does not compare the submitted key against `GA_API_KEY`

#### Scenario: Successful login resets the throttle counter
- **WHEN** `POST /dashboard/login` is called with the correct `ga_api_key` after one or more prior failures from the same source
- **THEN** the transport returns HTTP 200, issues a session cookie, and the failure counter for that source is reset to zero

#### Scenario: Failed logins from distinct sources are tracked independently
- **WHEN** `POST /dashboard/login` is called with an incorrect key from source A until A is throttled, and then called with an incorrect key from source B
- **THEN** source B's request is evaluated normally (not rejected) because its own counter has not reached the maximum

#### Scenario: XFF header does not influence throttle source key
- **WHEN** `POST /dashboard/login` is called with a forged `X-Forwarded-For` header
- **THEN** the throttle source key is derived from the ASGI client address, not from `X-Forwarded-For`

### Requirement: Server-side revocable session store for dashboard sessions
The transport SHALL store `gs_session` tokens in `security.SessionStore`, issuing and validating them through `.issue()` and `.validate()` for revocation and expiry. `GA_PORTAL_SESSION_TTL_SECS` SHALL be injected into the crew environment by `install.sh` to configure the lifetime.

#### Scenario: Issued token is valid until expiry
- **WHEN** a `gs_session` token is issued by a successful `POST /dashboard/login`
- **THEN** `GET /dashboard/auth` returns HTTP 200 for subsequent requests presenting that token, until the configured session lifetime elapses

#### Scenario: Revoked token is immediately rejected
- **WHEN** a `gs_session` token is revoked (e.g. via `POST /dashboard/logout`)
- **THEN** `GET /dashboard/auth` returns HTTP 401 for any subsequent request presenting that token, even if the token's natural expiry has not been reached

#### Scenario: Session TTL configured via GA_PORTAL_SESSION_TTL_SECS takes effect
- **WHEN** `GA_PORTAL_SESSION_TTL_SECS` is set in `ghostship.conf` and `install.sh` is run
- **THEN** the generated `compose.yml` contains `GA_PORTAL_SESSION_TTL_SECS` in the transport environment
- **THEN** `gs_session` tokens expire after that many seconds

### Requirement: Dashboard logout endpoint
The transport SHALL expose `POST /dashboard/logout` as a public route. When called with a valid `gs_session` cookie, it SHALL validate the CSRF token (same token embedded in the login form and validated on login), revoke the session server-side, and respond with a `Set-Cookie` header that clears the cookie in the browser. When called without a valid session cookie it SHALL return HTTP 401. When called without a valid CSRF token it SHALL return HTTP 403.

#### Scenario: Logout revokes session and clears cookie
- **WHEN** `POST /dashboard/logout` is called with a valid `gs_session` cookie and a correct CSRF token
- **THEN** the transport returns HTTP 200, the `gs_session` token is revoked in `SessionStore`, and the response includes a `Set-Cookie` header with `gs_session=; Max-Age=0; Path=/` (or equivalent cookie-clearing attributes)

#### Scenario: Logout without a valid session returns 401
- **WHEN** `POST /dashboard/logout` is called with no `gs_session` cookie, an expired token, or a revoked token
- **THEN** the transport returns HTTP 401 and no session state is modified

#### Scenario: Logout without a valid CSRF token returns 403
- **WHEN** `POST /dashboard/logout` is called with a valid `gs_session` cookie but a missing or incorrect CSRF token
- **THEN** the transport returns HTTP 403 and the session is NOT revoked

### Requirement: WebSocket upgrade authenticated by gs_session cookie, not app token

The dashboard WebSocket upgrade SHALL authenticate solely with the validated `gs_session` cookie from the SPA load and bypass `forward_auth`. It SHALL NOT set or forward `X-App-Token` or another app token to the gateway; preserve this across gateway upgrades.

#### Scenario: WS upgrade proxy carries no app token
- **WHEN** a browser with a valid `gs_session` cookie opens a WebSocket connection to the crew dashboard
- **THEN** the transport proxies the upgrade to the upstream crew gateway with the `X-Transport-Token` header set and no `X-App-Token` header present

#### Scenario: Cookie-authenticated WS connection receives the full crew event stream
- **WHEN** a logged-in operator's dashboard WS connection is established (authenticated via `gs_session`, carrying no app token)
- **THEN** the upstream crew gateway delivers the full crew session event stream (turn started, turn ended, new message) without per-app filtering

#### Scenario: Per-app WS scoping does not apply to cookie-authenticated connections
- **WHEN** the upstream KiroCrew gateway has per-app WS event scoping enabled (filtering connections that present an `X-App-Token`)
- **THEN** a cookie-authenticated dashboard WS connection is not subject to that filter and continues to receive all crew events

### Requirement: Forward_auth port parameter is validated against the configured range
`/dashboard/auth` SHALL reject ports outside the configured dashboard range with HTTP 400 before crew lookup. A port within range but unmapped to a crew SHALL return HTTP 200 without crew-specific cookie injection.

#### Scenario: Port below the configured range is rejected
- **WHEN** `GET /dashboard/auth` is called with a `port` query parameter whose integer value is less than `ga_dashboard_port_base`
- **THEN** the transport returns HTTP 400 without performing a crew lookup

#### Scenario: Port above the configured range is rejected
- **WHEN** `GET /dashboard/auth` is called with a `port` query parameter whose integer value is greater than or equal to `ga_dashboard_port_base + ga_dashboard_port_range_size`
- **THEN** the transport returns HTTP 400 without performing a crew lookup

#### Scenario: Port within the configured range proceeds normally
- **WHEN** `GET /dashboard/auth` is called with a `port` query parameter whose integer value is within the configured range
- **THEN** the transport proceeds to crew lookup; a valid session returns HTTP 200 regardless of whether the port maps to a known crew

#### Scenario: Missing port parameter is not rejected
- **WHEN** `GET /dashboard/auth` is called with no `port` query parameter
- **THEN** the transport does not return HTTP 400; it falls back to other port-resolution methods (e.g. `x-dashboard-port` header)

#### Scenario: Non-integer port parameter is rejected
- **WHEN** `GET /dashboard/auth` is called with a `port` query parameter that is not a valid integer (e.g. `port=abc`)
- **THEN** the transport returns HTTP 400 without performing a crew lookup

### Requirement: handle_auth and handle_logout_post have direct unit tests

`tests/unit/test_dashboard.py` SHALL include direct tests for `DashboardGate.handle_auth`
and `DashboardGate.handle_logout_post` covering the following cases:

- `handle_auth` with a valid unexpired `gs_session` cookie returns HTTP 200
- `handle_auth` with an expired `gs_session` cookie returns HTTP 401
- `handle_auth` with a revoked `gs_session` cookie (after logout) returns HTTP 401
- `handle_logout_post` revokes the session so subsequent `handle_auth` calls return 401

#### Scenario: Valid session passes auth check
- **WHEN** `handle_auth` is called with a request carrying a valid `gs_session` cookie
- **THEN** the response status is 200

#### Scenario: Expired session fails auth check
- **WHEN** `handle_auth` is called with a request carrying an expired `gs_session` cookie
- **THEN** the response status is 401

#### Scenario: Revoked session fails auth check after logout
- **WHEN** `handle_logout_post` is called for a session and then `handle_auth` is called with that session's cookie
- **THEN** `handle_auth` returns 401

### Requirement: Dashboard login accepts only validated local redirects

Dashboard login SHALL validate the submitted `next` value after NFKC normalisation and replace unsafe or empty values with `/`. On success it SHALL return the validated target in the JSON response. The browser SHALL redirect using that response value.

#### Scenario: Server-side validated next URL is used for redirect
- **WHEN** `POST /dashboard/login` succeeds with a valid `ga_api_key` and a `next` field in the form body
- **THEN** the JSON 200 response includes a `next` field containing the server-sanitised URL (output of `_validate_next_url()`)
- **THEN** the client redirects to that server-provided value, not the raw submitted value

#### Scenario: Crafted form next value is sanitised server-side
- **WHEN** `POST /dashboard/login` receives a form body where `next` is `//evil.com`
- **THEN** the JSON 200 response includes `next: "/"` (sanitised fallback)
- **THEN** the browser is redirected to `/`, not to `//evil.com`

#### Scenario: Relative path passes validation

- **WHEN** `_validate_next_url` is called with `/crews/abc`
- **THEN** it returns `/crews/abc` unchanged

#### Scenario: Protocol-relative URL is rejected

- **WHEN** `_validate_next_url` is called with `//evil.com/steal`
- **THEN** it returns `/`

#### Scenario: Absolute URL is rejected

- **WHEN** `_validate_next_url` is called with `https://evil.com`
- **THEN** it returns `/`

#### Scenario: JavaScript URI is rejected

- **WHEN** `_validate_next_url` is called with `javascript:alert(1)`
- **THEN** it returns `/`

#### Scenario: NFKC-normalised lookalike is rejected

- **WHEN** `_validate_next_url` is called with a Unicode lookalike that normalises to `//evil.com`
- **THEN** it returns `/`

#### Scenario: Empty string returns slash

- **WHEN** `_validate_next_url` is called with an empty string
- **THEN** it returns `/`

### Requirement: Dashboard login issues a protected session cookie

After CSRF validation, dashboard login SHALL compare the submitted API key in constant time. A valid key SHALL issue a random 32-byte hex `gs_session` token stored in the revocable in-memory session store with a configurable TTL defaulting to 24 hours. The cookie SHALL use `HttpOnly`, `SameSite=Lax`, and `Path=/`, with `Secure` when portal TLS is enabled. An invalid key returns HTTP 401 without issuing a session.

#### Scenario: Valid API key returns session cookie
- **WHEN** `POST /dashboard/login` is sent with a correct `ga_api_key`
- **THEN** the response is 200 with a `Set-Cookie: gs_session=<token>` header
- **THEN** the token is stored for future forward-auth checks

#### Scenario: Invalid API key returns 401
- **WHEN** `POST /dashboard/login` is sent with an incorrect `ga_api_key`
- **THEN** the response is 401 with no Set-Cookie header

#### Scenario: Secure flag set when TLS is enabled
- **WHEN** `POST /dashboard/login` succeeds and `ga_portal_tls_mode` is not `"off"` (e.g. `"auto"` or `"manual"`)
- **THEN** the `Set-Cookie` response header includes the `Secure` attribute

#### Scenario: Secure flag omitted when TLS is disabled
- **WHEN** `POST /dashboard/login` succeeds and `ga_portal_tls_mode` is `"off"`
- **THEN** the `Set-Cookie` response header does NOT include the `Secure` attribute

#### Scenario: gs_session cookie has SameSite=Lax

- **WHEN** a successful `POST /dashboard/login` issues a `gs_session` cookie
- **THEN** the `Set-Cookie` header SHALL include `SameSite=Lax`
