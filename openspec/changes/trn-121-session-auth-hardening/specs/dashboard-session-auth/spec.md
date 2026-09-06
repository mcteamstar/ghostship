## Purpose

Hardens the transport's dashboard login gate with brute-force throttling, a server-side revocable session store, an explicit logout endpoint, and a TLS-conditional `Secure` cookie flag.

## ADDED Requirements

### Requirement: Brute-force throttle on dashboard login
The transport SHALL apply a sliding-window failed-attempt throttle to `POST /dashboard-login`, keyed on the request's source IP. When the number of failed attempts from a source within the configured window reaches the maximum, the endpoint SHALL return HTTP 429 without evaluating the submitted credential. A successful login SHALL reset the counter for that source.

#### Scenario: Excessive failed logins from one source are rejected
- **WHEN** `POST /dashboard-login` is called with an incorrect `ga_api_key` more than the configured maximum number of times within the throttle window from the same source IP
- **THEN** the transport returns HTTP 429 and does not compare the submitted key against `GA_API_KEY`

#### Scenario: Successful login resets the throttle counter
- **WHEN** `POST /dashboard-login` is called with the correct `ga_api_key` after one or more prior failures from the same source
- **THEN** the transport returns HTTP 200, issues a session cookie, and the failure counter for that source is reset to zero

#### Scenario: Failed logins from distinct sources are tracked independently
- **WHEN** `POST /dashboard-login` is called with an incorrect key from source A until A is throttled, and then called with an incorrect key from source B
- **THEN** source B's request is evaluated normally (not rejected) because its own counter has not reached the maximum

### Requirement: Server-side revocable session store for dashboard sessions
The transport SHALL manage `gs_session` tokens using `security.SessionStore` rather than a plain dict. Session issuance and validation SHALL go through `SessionStore.issue()` and `SessionStore.validate()` respectively, so that tokens can be revoked server-side and expire according to the store's `lifetime_secs`.

#### Scenario: Issued token is valid until expiry
- **WHEN** a `gs_session` token is issued by a successful `POST /dashboard-login`
- **THEN** `GET /dashboard-auth` returns HTTP 200 for subsequent requests presenting that token, until the configured session lifetime elapses

#### Scenario: Revoked token is immediately rejected
- **WHEN** a `gs_session` token is revoked (e.g. via `POST /dashboard-logout`)
- **THEN** `GET /dashboard-auth` returns HTTP 401 for any subsequent request presenting that token, even if the token's natural expiry has not been reached

### Requirement: Dashboard logout endpoint
The transport SHALL expose `POST /dashboard-logout` as a public route. When called with a valid `gs_session` cookie, it SHALL revoke the session server-side and respond with a `Set-Cookie` header that clears the cookie in the browser. When called without a valid session cookie it SHALL return HTTP 401.

#### Scenario: Logout revokes session and clears cookie
- **WHEN** `POST /dashboard-logout` is called with a valid `gs_session` cookie
- **THEN** the transport returns HTTP 200, the `gs_session` token is revoked in `SessionStore`, and the response includes a `Set-Cookie` header with `gs_session=; Max-Age=0; Path=/` (or equivalent cookie-clearing attributes)

#### Scenario: Logout without a valid session returns 401
- **WHEN** `POST /dashboard-logout` is called with no `gs_session` cookie, an expired token, or a revoked token
- **THEN** the transport returns HTTP 401 and no session state is modified

### Requirement: TLS-conditional Secure cookie flag on gs_session
The transport SHALL set the `Secure` attribute on the `gs_session` cookie only when `ga_portal_tls_mode` is not `"off"`. When `ga_portal_tls_mode` is `"off"` the cookie SHALL be issued without the `Secure` attribute so that plain-HTTP deployments function correctly.

#### Scenario: Secure flag set when TLS is enabled
- **WHEN** `POST /dashboard-login` succeeds and `ga_portal_tls_mode` is not `"off"` (e.g. `"auto"` or `"manual"`)
- **THEN** the `Set-Cookie` response header includes the `Secure` attribute

#### Scenario: Secure flag omitted when TLS is disabled
- **WHEN** `POST /dashboard-login` succeeds and `ga_portal_tls_mode` is `"off"`
- **THEN** the `Set-Cookie` response header does NOT include the `Secure` attribute
