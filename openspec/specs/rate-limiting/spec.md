# Rate Limiting Specification

## Purpose

Defines the HTTP request rate limiting enforced by the Ghost Academy transport. Rate
limiting bounds the request rate any caller can sustain against specific endpoints,
complementing the existing brute-force `Throttle` (which tracks *failed auth attempts*)
with a mechanism that tracks *request volume* regardless of outcome.

## Requirements

### Requirement: Sliding-window RateLimiter primitive

`RateLimiter` in `transport/security.py` SHALL maintain a thread-safe, in-memory sliding window per string key, bounded by integer `max_requests` and floating-point `window_secs`. `record` atomically allows and records or denies without recording; `is_limited` checks without recording; each call SHALL prune expired timestamps.

#### Scenario: Within limit — request allowed
- **WHEN** a caller has made fewer than `max_requests` requests in the last `window_secs`
- **THEN** `record(key)` returns `True` and the request count increments by 1

#### Scenario: Limit reached — request denied
- **WHEN** a caller has made exactly `max_requests` requests within the last `window_secs`
- **THEN** `record(key)` returns `False` and the request count is not incremented

#### Scenario: Window slides — old requests expire
- **WHEN** a caller made `max_requests` requests but all of them are older than `window_secs`
- **THEN** `record(key)` returns `True` — the window has slid past those old timestamps

#### Scenario: Thread safety
- **WHEN** two threads call `record(key)` concurrently for the same key at the limit boundary
- **THEN** exactly one call returns `True` and the other returns `False`; the recorded
  count never exceeds `max_requests` within the window
### Requirement: RateLimitMiddleware ASGI layer

The system SHALL provide a `RateLimitMiddleware` ASGI class in `transport/server.py`
that applies per-endpoint rate limiting to all inbound HTTP requests. The middleware
SHALL sit outside `BearerAuthMiddleware` in the middleware stack so that all callers,
including unauthenticated ones, are subject to limits. Non-HTTP ASGI scopes (e.g.
WebSocket, lifespan) SHALL pass through unchanged.

#### Scenario: Request within limit passes through
- **WHEN** a caller's request to a rate-limited endpoint is within the configured limit
- **THEN** the request is forwarded to the next middleware and the caller receives the
  normal response

#### Scenario: Request exceeds limit — 429 returned
- **WHEN** a caller's request to a rate-limited endpoint exceeds the configured limit
- **THEN** the middleware returns `429 Too Many Requests` with:
  - `Content-Type: text/plain; charset=utf-8`
  - `Retry-After: <window_secs>` (integer seconds, full window duration)
  - Body: `Rate limit exceeded. Retry after <window_secs> seconds.`
  - The downstream handler is NOT invoked

#### Scenario: Health and version endpoints are exempt
- **WHEN** a request targets `/health` or `/version`
- **THEN** the middleware applies no rate check and passes the request through
  unconditionally — these paths must never return 429

#### Scenario: Unlimied endpoint passes through
- **WHEN** a request targets a path not covered by any registered limiter
  (e.g. `/logout`, `/crews/{id}/ui/`)
- **THEN** the middleware passes the request through without any rate check

### Requirement: Composite caller-identity key

Rate limiting SHALL group unauthenticated requests by resolved source IP. Only an authenticated API key SHALL add its hash to the existing composite key. Raw keys SHALL NOT be stored. Trusted peers retain existing forwarded-address resolution; other peers use their ASGI address.

#### Scenario: No API key uses an IP-only bucket
- **WHEN** a request arrives without an Authorization header
- **THEN** its limiter key is the resolved source IP alone

#### Scenario: API key is hashed into the caller key
- **WHEN** a request presents the currently configured API key
- **THEN** its limiter key uses SHA-256(api_key)[:8] and the resolved source IP without storing the raw key

#### Scenario: Untrusted peer cannot spoof the source address
- **WHEN** a request comes from a peer outside `GA_TRUSTED_PROXY_CIDR` and supplies `X-Forwarded-For`
- **THEN** the source IP is the ASGI peer address and the header is ignored

#### Scenario: Trusted peer uses the first forwarded hop
- **WHEN** a trusted proxy sends `X-Forwarded-For: 10.0.0.1, 192.168.1.5`
- **THEN** the source IP is `10.0.0.1`

#### Scenario: Trusted peer without a forwarded header falls back
- **WHEN** a request comes from a trusted peer without an `X-Forwarded-For` header
- **THEN** the source IP is the ASGI peer address

#### Scenario: Same IP and same key share a bucket
- **WHEN** two requests arrive from the same source IP with the same API key
- **THEN** they share the same rate-limit bucket

#### Scenario: Same IP and different keys use separate buckets
- **WHEN** two requests arrive from the same source IP with different API keys
- **THEN** they use separate rate-limit buckets

#### Scenario: Unset trusted-proxy configuration ignores forwarded headers
- **WHEN** `GA_TRUSTED_PROXY_CIDR` is unset or empty and a request carries `X-Forwarded-For`
- **THEN** the middleware uses the ASGI peer address

### Requirement: Endpoint limiter state has a finite capacity

Each endpoint limiter SHALL cap tracked keys and reclaim expired keys across callers while preserving atomic quota checks.

#### Scenario: Limiter has no free bucket
- **WHEN** a new key arrives at capacity after expiry reclamation
- **THEN** it receives the existing HTTP 429 response and active buckets are preserved

#### Scenario: Inactive bucket expires
- **WHEN** a key has no hits left in its window
- **THEN** its capacity is reclaimed without needing another request from that key

### Requirement: Per-endpoint default limits

The transport SHALL limit `GET /login` to 30/60s, `POST /login` to 5/300s, `/files/*` to 60/60s, `/crews/{id}/api/*` to 120/60s, and `/mcp` to 300/60s. Each is independently overridable; `/crews/{id}/ui/*` is not limited.

#### Scenario: GET /login — polling allowed, hammering blocked
- **WHEN** a caller makes 30 `GET /login` requests within 60 seconds
- **THEN** the 31st request within that window returns 429

#### Scenario: POST /login — tight limit enforces deliberate use
- **WHEN** a caller makes 5 `POST /login` requests within 300 seconds
- **THEN** the 6th request within that window returns 429

#### Scenario: /mcp — headroom for multi-tool orchestration
- **WHEN** a caller makes 300 requests to `/mcp` within 60 seconds
- **THEN** the 301st request within that window returns 429

#### Scenario: /files/* — protects git subprocess execution
- **WHEN** a caller makes 60 requests to `/files/` within 60 seconds
- **THEN** the 61st request within that window returns 429

#### Scenario: /crews/*/api/* — proxied crew API
- **WHEN** a caller makes 120 requests to a `/crews/{id}/api/` path within 60 seconds
- **THEN** the 121st request within that window returns 429
### Requirement: Per-endpoint env-var overrides

At startup, `GA_RATE_LIMIT_LOGIN_GET`, `GA_RATE_LIMIT_LOGIN_POST`, `GA_RATE_LIMIT_MCP`, `GA_RATE_LIMIT_FILES`, and `GA_RATE_LIMIT_CREW_API` SHALL override their endpoint defaults.

#### Scenario: Valid override is applied
- **WHEN** `GA_RATE_LIMIT_MCP=600:120` is set
- **THEN** the `/mcp` limiter allows 600 requests per 120-second window

#### Scenario: Malformed override falls back to default with a warning
- **WHEN** `GA_RATE_LIMIT_FILES=notanumber` is set
- **THEN** the `/files/*` limiter uses the default (60 req / 60 s) and a `WARNING` log
  entry names `GA_RATE_LIMIT_FILES` and describes the parse failure

### Requirement: Rate-limit overrides are validated and can be disabled

Override values SHALL use positive `<count>:<window_secs>` integers; invalid values SHALL use defaults and log a warning naming the variable. `GA_RATE_LIMIT_ENABLED` SHALL disable the whole middleware when false.

#### Scenario: Master switch disables all limiting
- **WHEN** `GA_RATE_LIMIT_ENABLED=false` is set
- **THEN** `RateLimitMiddleware` is not added to the stack and all requests pass through
  without any rate check; an `INFO` log entry confirms rate limiting is disabled
### Requirement: In-memory state only

Rate limiter state is held in process memory and is not persisted. Restarting the
transport process resets all counters. This is the intended behaviour for a
single-process local deployment and SHALL be documented as such in
`docs/configuration.md`.

#### Scenario: Process restart clears all counters
- **WHEN** the transport process is restarted
- **THEN** all rate-limit counters start from zero; no caller is pre-limited based on
  pre-restart history
