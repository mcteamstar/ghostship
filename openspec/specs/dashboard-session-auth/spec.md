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
The transport SHALL manage `gs_session` tokens using `security.SessionStore` rather than a plain dict. Session issuance and validation SHALL go through `SessionStore.issue()` and `SessionStore.validate()` respectively, so that tokens can be revoked server-side and expire according to the store's `lifetime_secs`. The session lifetime SHALL be configurable via `GA_PORTAL_SESSION_TTL_SECS`, which SHALL be injected into the crew container environment by `install.sh` so operator configuration takes effect.

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

### Requirement: TLS-conditional Secure cookie flag on gs_session
The transport SHALL set the `Secure` attribute on the `gs_session` cookie only when `ga_portal_tls_mode` is not `"off"`. When `ga_portal_tls_mode` is `"off"` the cookie SHALL be issued without the `Secure` attribute so that plain-HTTP deployments function correctly.

#### Scenario: Secure flag set when TLS is enabled
- **WHEN** `POST /dashboard/login` succeeds and `ga_portal_tls_mode` is not `"off"` (e.g. `"auto"` or `"manual"`)
- **THEN** the `Set-Cookie` response header includes the `Secure` attribute

#### Scenario: Secure flag omitted when TLS is disabled
- **WHEN** `POST /dashboard/login` succeeds and `ga_portal_tls_mode` is `"off"`
- **THEN** the `Set-Cookie` response header does NOT include the `Secure` attribute

### Requirement: Server-side open-redirect protection on login redirect
The transport SHALL use the server-validated `next` URL (from `_validate_next_url()`) when redirecting after a successful login, not the raw value submitted in the form body. The server SHALL return the sanitised `next` URL in the JSON 200 response body; the client-side handler SHALL redirect only to that server-provided value.

#### Scenario: Server-side validated next URL is used for redirect
- **WHEN** `POST /dashboard/login` succeeds with a valid `ga_api_key` and a `next` field in the form body
- **THEN** the JSON 200 response includes a `next` field containing the server-sanitised URL (output of `_validate_next_url()`)
- **THEN** the client redirects to that server-provided value, not the raw submitted value

#### Scenario: Crafted form next value is sanitised server-side
- **WHEN** `POST /dashboard/login` receives a form body where `next` is `//evil.com`
- **THEN** the JSON 200 response includes `next: "/"` (sanitised fallback)
- **THEN** the browser is redirected to `/`, not to `//evil.com`


### Requirement: WebSocket upgrade authenticated by gs_session cookie, not app token

The transport WS proxy route (the `Connection: Upgrade` route in `CaddyPortal.register_crew`) SHALL authenticate WebSocket upgrade requests solely via the `gs_session` session cookie inherited from the dashboard SPA's initial HTTP load. The WS proxy route SHALL NOT set or forward an `X-App-Token` header (or any per-app token) to the upstream crew gateway. The WS route bypasses `forward_auth` because the browser context already carries a validated `gs_session` from the SPA load; this invariant MUST be preserved across gateway version upgrades.

#### Scenario: WS upgrade proxy carries no app token
- **WHEN** a browser with a valid `gs_session` cookie opens a WebSocket connection to the crew dashboard
- **THEN** the transport proxies the upgrade to the upstream crew gateway with the `X-Transport-Token` header set and no `X-App-Token` header present

#### Scenario: Cookie-authenticated WS connection receives the full crew event stream
- **WHEN** a logged-in operator's dashboard WS connection is established (authenticated via `gs_session`, carrying no app token)
- **THEN** the upstream crew gateway delivers the full crew session event stream (turn started, turn ended, new message) without per-app filtering

#### Scenario: Per-app WS scoping does not apply to cookie-authenticated connections
- **WHEN** the upstream KiroCrew gateway has per-app WS event scoping enabled (filtering connections that present an `X-App-Token`)
- **THEN** a cookie-authenticated dashboard WS connection is not subject to that filter and continues to receive all crew events

### Requirement: Per-session CSRF token uniqueness

The transport SHALL generate a fresh CSRF token for each new dashboard session
rather than reusing a single process-wide token.

#### Scenario: Two sessions receive distinct CSRF tokens

- **WHEN** two separate dashboard sessions are initiated
- **THEN** each session's `gs_csrf` cookie value SHALL be distinct

#### Scenario: CSRF token changes after session expiry

- **WHEN** a session expires and a new session is initiated
- **THEN** the new session's `gs_csrf` cookie value SHALL differ from the expired session's value

### Requirement: CSRF token rejection for forged values

The dashboard login endpoint SHALL reject requests that present a CSRF token
not matching the session's issued token.

#### Scenario: Forged CSRF token returns 403

- **WHEN** `POST /dashboard/login` is called with a valid `gs_csrf` cookie but a mismatched `X-CSRF-Token` header (or vice versa)
- **THEN** the transport SHALL return HTTP 403 without evaluating the API key

#### Scenario: Absent CSRF token returns 403

- **WHEN** `POST /dashboard/login` is called with no `gs_csrf` cookie or no `X-CSRF-Token` header
- **THEN** the transport SHALL return HTTP 403

#### Scenario: Matching CSRF token proceeds to key evaluation

- **WHEN** `POST /dashboard/login` is called with a matching `gs_csrf` cookie and `X-CSRF-Token` header
- **THEN** the transport SHALL proceed to evaluate the submitted API key (and return 200 on success)

### Requirement: SameSite=Lax on gs_session cookie

The `gs_session` cookie SHALL carry `SameSite=Lax` to mitigate cross-site
request forgery while still permitting navigation-driven GET requests.

#### Scenario: gs_session cookie has SameSite=Lax

- **WHEN** a successful `POST /dashboard/login` issues a `gs_session` cookie
- **THEN** the `Set-Cookie` header SHALL include `SameSite=Lax`

### Requirement: Open-redirect protection validates relative paths

`_validate_next_url` SHALL reject any `next` parameter that could redirect the
browser to an external origin or execute arbitrary code, after NFKC
normalisation.

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
