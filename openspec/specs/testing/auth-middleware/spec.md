# transport/auth-unit-tests Specification

## Purpose

Defines the testable behavioral contract for `transport/auth.py` — the ASGI middleware stack that enforces bearer API-key authentication, transport-secret gating, per-endpoint rate limiting, and HTTP security headers. Every requirement here SHALL have a corresponding passing test in `tests/unit/test_auth.py`.

## Requirements

### Requirement: _parse_bearer_token extracts well-formed tokens

The helper SHALL return the token string when the Authorization header value is a well-formed `Bearer <token>` (case-insensitive scheme, single space, no embedded spaces in the token), and SHALL return `None` for all other inputs.

#### Scenario: Well-formed Bearer header returns token
- **WHEN** `_parse_bearer_token("Bearer abc123")` is called
- **THEN** the return value is `"abc123"`

#### Scenario: Case-insensitive scheme is accepted
- **WHEN** `_parse_bearer_token("BEARER mytoken")` is called
- **THEN** the return value is `"mytoken"`

#### Scenario: Missing scheme returns None
- **WHEN** `_parse_bearer_token("abc123")` is called
- **THEN** the return value is `None`

#### Scenario: Wrong scheme returns None
- **WHEN** `_parse_bearer_token("Basic abc123")` is called
- **THEN** the return value is `None`

#### Scenario: Token with embedded space returns None
- **WHEN** `_parse_bearer_token("Bearer a b")` is called
- **THEN** the return value is `None`

#### Scenario: Empty string returns None
- **WHEN** `_parse_bearer_token("")` is called
- **THEN** the return value is `None`

#### Scenario: Header shorter than 8 chars returns None
- **WHEN** `_parse_bearer_token("Bear x")` is called (length < 8)
- **THEN** the return value is `None`

### Requirement: _parse_rate_limit_var parses env var or returns default

The helper SHALL parse a `"<count>:<window_secs>"` env var value and return `(count, window)` as positive integers. On any parse failure it SHALL return the supplied defaults and emit a WARNING log line.

#### Scenario: Valid env var is parsed
- **WHEN** the env var is set to `"10:60"`
- **THEN** the return value is `(10, 60)`

#### Scenario: Env var not set returns defaults
- **WHEN** the env var is absent
- **THEN** the return value is the default `(count, window)` pair supplied by the caller

#### Scenario: Non-integer value returns defaults and logs warning
- **WHEN** the env var is set to `"notanumber:60"`
- **THEN** the return value is the supplied defaults and a WARNING is emitted

#### Scenario: Zero count returns defaults and logs warning
- **WHEN** the env var is set to `"0:60"`
- **THEN** the return value is the supplied defaults and a WARNING is emitted

#### Scenario: Negative window returns defaults and logs warning
- **WHEN** the env var is set to `"10:-1"`
- **THEN** the return value is the supplied defaults and a WARNING is emitted

### Requirement: _build_rate_limiters respects master switch

The factory SHALL return `None` when `GA_RATE_LIMIT_ENABLED=false`, and a populated dict of `RateLimiter` instances otherwise.

#### Scenario: Master switch false returns None
- **WHEN** `GA_RATE_LIMIT_ENABLED` is `"false"`
- **THEN** `_build_rate_limiters()` returns `None`

#### Scenario: Master switch true returns populated dict
- **WHEN** `GA_RATE_LIMIT_ENABLED` is `"true"` (or absent)
- **THEN** `_build_rate_limiters()` returns a dict keyed by the known endpoint names

### Requirement: TransportSecretMiddleware enforces X-Transport-Token gate

When `transport_secret` is non-empty, the middleware SHALL allow requests carrying the correct `X-Transport-Token` value and reject all others with HTTP 401. When `transport_secret` is empty the middleware SHALL be a transparent pass-through.

#### Scenario: Correct token passes through
- **WHEN** `transport_secret` is `"s3cr3t"` AND the request carries `X-Transport-Token: s3cr3t`
- **THEN** the downstream app is called and no 401 is sent

#### Scenario: Wrong token returns 401
- **WHEN** `transport_secret` is `"s3cr3t"` AND the request carries `X-Transport-Token: wrong`
- **THEN** the middleware returns HTTP 401 and the downstream app is NOT called

#### Scenario: Missing token returns 401
- **WHEN** `transport_secret` is `"s3cr3t"` AND the request has no `X-Transport-Token` header
- **THEN** the middleware returns HTTP 401

#### Scenario: Empty secret is a pass-through
- **WHEN** `transport_secret` is `""` or absent
- **THEN** all requests pass through regardless of the `X-Transport-Token` header value

#### Scenario: Constant-time comparison is used
- **WHEN** `TransportSecretMiddleware` validates the token
- **THEN** the comparison uses `hmac.compare_digest`, not `==`, so timing does not leak the secret length

#### Scenario: Non-HTTP scope passes through
- **WHEN** a WebSocket or lifespan scope is received
- **THEN** the scope is forwarded to the downstream app unchanged

### Requirement: RateLimitMiddleware enforces per-endpoint sliding-window limits

The middleware SHALL track request counts per caller identity and return HTTP 429 with a `Retry-After` header when the limit is exceeded. `/health` and `/version` SHALL be unconditionally exempt.

#### Scenario: Health endpoint is exempt
- **WHEN** a GET request arrives at `/health`
- **THEN** no rate-limit check is performed and the request passes through

#### Scenario: Version endpoint is exempt
- **WHEN** a GET request arrives at `/version`
- **THEN** no rate-limit check is performed and the request passes through

#### Scenario: First request within limit passes
- **WHEN** a request is within the window count
- **THEN** the downstream app is called

#### Scenario: Request over limit returns 429
- **WHEN** a caller exceeds the configured request count within the window
- **THEN** the middleware returns HTTP 429 with a `Retry-After` header and the downstream app is NOT called

#### Scenario: Caller key uses IP only when no bearer token is present
- **WHEN** no `Authorization` header is present
- **THEN** the rate-limit key is the source IP

#### Scenario: Caller key hashes bearer token when present
- **WHEN** an `Authorization: Bearer <token>` header is present
- **THEN** the rate-limit key is `SHA-256(token)[:8]:<ip>` and the raw token is not stored

#### Scenario: Unmatched path passes through without rate check
- **WHEN** a request path does not match any registered endpoint pattern
- **THEN** no rate check is performed and the request passes through

#### Scenario: POST /login is matched to login_post limiter
- **WHEN** a `POST /login` request arrives
- **THEN** the `login_post` limiter is applied

#### Scenario: GET /login is matched to login_get limiter
- **WHEN** a `GET /login` request arrives
- **THEN** the `login_get` limiter is applied

#### Scenario: /files/ path is matched to files limiter
- **WHEN** a request path starts with `/files/`
- **THEN** the `files` limiter is applied

#### Scenario: /crews/<id>/api path is matched to crew_api limiter
- **WHEN** a request path matches `/crews/<id>/api` or `/crews/<id>/api/<sub>`
- **THEN** the `crew_api` limiter is applied

#### Scenario: /mcp path is matched to mcp limiter
- **WHEN** a request path starts with `/mcp`
- **THEN** the `mcp` limiter is applied

#### Scenario: GET /dashboard/auth is matched to dashboard_auth limiter
- **WHEN** a `GET /dashboard/auth` request arrives
- **THEN** the `dashboard_auth` limiter is applied

#### Scenario: POST /dashboard/login is matched to dashboard_auth limiter
- **WHEN** a `POST /dashboard/login` request arrives
- **THEN** the `dashboard_auth` limiter is applied

### Requirement: BearerAuthMiddleware enforces static API-key authentication

When `api_key` is non-empty, all HTTP requests (except public paths) SHALL require exactly one well-formed `Authorization: Bearer <key>` header matching the configured key. Requests with missing, duplicate, malformed, or wrong tokens SHALL receive HTTP 401. The `/health` path SHALL always pass through. When `api_key` is empty the bearer check SHALL be skipped entirely.

#### Scenario: Correct bearer token passes through to downstream app
- **WHEN** `api_key` is set AND the request carries `Authorization: Bearer <correct-key>`
- **THEN** the downstream app receives the request and no 401 is emitted

#### Scenario: Wrong bearer token returns 401
- **WHEN** `api_key` is set AND the request carries `Authorization: Bearer <wrong-key>`
- **THEN** the middleware returns HTTP 401 with `WWW-Authenticate: Bearer`

#### Scenario: Missing Authorization header returns 401
- **WHEN** `api_key` is set AND no `Authorization` header is present
- **THEN** the middleware returns HTTP 401

#### Scenario: Duplicate Authorization headers return 401
- **WHEN** `api_key` is set AND the request carries two `Authorization` headers
- **THEN** the middleware returns HTTP 401

#### Scenario: Malformed Authorization header returns 401
- **WHEN** `api_key` is set AND the request carries `Authorization: NotBearer abc`
- **THEN** the middleware returns HTTP 401

#### Scenario: /health bypasses bearer check
- **WHEN** `api_key` is set AND the request path is `/health`
- **THEN** the request passes through without an auth check

#### Scenario: api_key empty is a transparent pass-through
- **WHEN** `api_key` is `""` (disabled)
- **THEN** all requests pass through regardless of the Authorization header

#### Scenario: Constant-time comparison used for token validation
- **WHEN** `BearerAuthMiddleware` validates the bearer token
- **THEN** the comparison uses `hmac.compare_digest`

#### Scenario: Audit event is emitted on rejection
- **WHEN** a bearer-token check fails
- **THEN** an audit event with `outcome="denied"` is emitted (via the security module's `audit_auth_event`)

#### Scenario: Public route is dispatched without auth check
- **WHEN** a path/method matches an entry in `public_routes`
- **THEN** the registered handler is called before any bearer check

#### Scenario: /files/ requests are forwarded to file_app bypassing bearer check
- **WHEN** the request path starts with `/files/` AND `file_app` is set
- **THEN** the file app receives the request without a bearer-token check

#### Scenario: Registered route is dispatched after successful auth
- **WHEN** bearer auth passes AND the path/method matches an entry in `routes`
- **THEN** the registered route handler is called instead of the downstream app

#### Scenario: WebSocket upgrade for /crews/<id>/ui is dispatched without HTTP auth
- **WHEN** an ASGI WebSocket scope arrives with path `/crews/<id>/ui/...`
- **THEN** the registered WS handler is called without any bearer-token check

### Requirement: SecurityHeadersMiddleware injects security headers on every response

The middleware SHALL add baseline security headers to every HTTP response and, when on HTTPS, a non-zero `Strict-Transport-Security` header. It SHALL detect HTTPS from the ASGI scheme or `X-Forwarded-Proto`. When `enforce_redirect` is enabled, plaintext HTTP requests SHALL be redirected 301 to HTTPS (control characters stripped from the redirect target).

#### Scenario: Security headers are added to responses
- **WHEN** a response passes through `SecurityHeadersMiddleware`
- **THEN** `X-Content-Type-Options: nosniff` and a Content-Security-Policy header are present in the response

#### Scenario: HSTS header added on HTTPS responses
- **WHEN** the incoming request is HTTPS (scheme or X-Forwarded-Proto)
- **THEN** the response includes `Strict-Transport-Security` with a non-zero `max-age`

#### Scenario: HSTS header absent on HTTP responses
- **WHEN** the incoming request is plain HTTP
- **THEN** no `Strict-Transport-Security` header is added

#### Scenario: X-Forwarded-Proto detection
- **WHEN** the ASGI scheme is `http` but the request carries `X-Forwarded-Proto: https`
- **THEN** `_is_https` returns `True`

#### Scenario: Enforce-redirect sends 301 on HTTP
- **WHEN** `enforce_redirect=True` AND the request is plain HTTP AND path is not `/health`
- **THEN** a 301 redirect to the HTTPS equivalent is returned

#### Scenario: Health probe is never redirected
- **WHEN** `enforce_redirect=True` AND the request path is `/health`
- **THEN** no redirect is issued; the downstream app handles the request

#### Scenario: Control characters stripped from redirect target
- **WHEN** `enforce_redirect=True` AND the request path or host contains a control character
- **THEN** the `Location` header value has all control characters removed before the redirect is sent

#### Scenario: Headers disabled when enable_headers=False
- **WHEN** `enable_headers=False`
- **THEN** no security headers are injected and the downstream app response is forwarded unchanged

#### Scenario: Non-HTTP scope passes through unchanged
- **WHEN** a WebSocket or lifespan scope arrives
- **THEN** it is forwarded to the downstream app without any header injection or redirect

### Requirement: _request_source extracts client IP from scope or Request object

The helper SHALL return the first hop from `X-Forwarded-For` when present, or the ASGI `client` IP otherwise. It SHALL accept both an ASGI scope dict and a Starlette Request object. It SHALL return `None` when no IP can be determined.

#### Scenario: X-Forwarded-For first hop returned from scope dict
- **WHEN** the ASGI scope dict contains an `X-Forwarded-For` header with `"1.2.3.4, 5.6.7.8"`
- **THEN** `_request_source` returns `"1.2.3.4"`

#### Scenario: ASGI client IP returned when no XFF header
- **WHEN** the scope has no `X-Forwarded-For` header AND `scope["client"]` is `("10.0.0.1", 1234)`
- **THEN** `_request_source` returns `"10.0.0.1"`

#### Scenario: None returned when source unavailable
- **WHEN** the scope has no XFF header and no `client` entry
- **THEN** `_request_source` returns `None`
