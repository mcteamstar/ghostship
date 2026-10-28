# Spec Delta

## MODIFIED Requirements

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
