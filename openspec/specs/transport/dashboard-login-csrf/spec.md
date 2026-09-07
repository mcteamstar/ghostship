# transport/dashboard/login-csrf Specification

## Purpose

Protects the dashboard login form (`GET /dashboard/login` → `POST /dashboard/login`) against cross-site request forgery by embedding a server-generated token in the form and validating it on submission.

## Requirements

### Requirement: CSRF token generated at startup
The transport SHALL generate a single cryptographically random CSRF token at process startup and hold it for the lifetime of the process. The token SHALL NOT change between requests.

#### Scenario: Token initialised on module load
- **WHEN** the transport process starts
- **THEN** `_dashboard_csrf_token` is set to a non-empty random hex string generated via `secrets.token_hex`

### Requirement: CSRF token embedded in dashboard login form
The transport SHALL embed the CSRF token as a hidden form field named `csrf_token` in the HTML returned by `GET /dashboard/login`.

#### Scenario: Token present in rendered form
- **WHEN** a client requests `GET /dashboard/login`
- **THEN** the response body contains `<input type="hidden" name="csrf_token"` with the current `_dashboard_csrf_token` value

### Requirement: CSRF token validated on POST /dashboard/login
The transport SHALL read the `csrf_token` field from the submitted form body and perform a constant-time comparison against `_dashboard_csrf_token`. A missing or mismatched token SHALL cause the handler to return HTTP 403 before any API-key check is performed.

#### Scenario: Correct CSRF token accepted
- **WHEN** `POST /dashboard/login` is called with the correct `csrf_token` value and a valid `ga_api_key`
- **THEN** the handler proceeds normally and returns HTTP 200 with a `Set-Cookie: gs_session=...` header

#### Scenario: Missing CSRF token rejected
- **WHEN** `POST /dashboard/login` is called without a `csrf_token` field in the form body
- **THEN** the handler returns HTTP 403 and no `gs_session` cookie is issued

#### Scenario: Wrong CSRF token rejected
- **WHEN** `POST /dashboard/login` is called with a `csrf_token` value that does not match `_dashboard_csrf_token`
- **THEN** the handler returns HTTP 403 and no `gs_session` cookie is issued

#### Scenario: CSRF check precedes API-key check
- **WHEN** `POST /dashboard/login` is called with a wrong `csrf_token` but a correct `ga_api_key`
- **THEN** the handler returns HTTP 403, not HTTP 200 or HTTP 401
