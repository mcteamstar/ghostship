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

