# Rate Limiting Specification

## Purpose

Defines the HTTP request rate limiting enforced by the Ghost Academy transport. Rate
limiting bounds the request rate any caller can sustain against specific endpoints,
complementing the existing brute-force `Throttle` (which tracks *failed auth attempts*)
with a mechanism that tracks *request volume* regardless of outcome.

## Requirements

### Requirement: Sliding-window RateLimiter primitive

The system SHALL provide a `RateLimiter` class in `transport/security.py` that
implements a sliding-window request counter. The class SHALL be keyed on arbitrary
string caller-identity keys, thread-safe, and hold state in memory only (no external
store). The window SHALL be defined by `max_requests` (integer) and `window_secs`
(float). The `record(key)` method SHALL atomically check whether the caller is within
the limit and, if so, record the request and return `True`; if the limit is exceeded it
SHALL return `False` without recording. The `is_limited(key)` method SHALL check
without recording. Expired timestamps (older than `window_secs`) SHALL be pruned on
each call so memory stays bounded by the number of requests within the current window.

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

The middleware SHALL derive a per-caller key from available request signals:

- **No API key presented**: key is the source IP address.
- **API key presented (valid or not yet verified)**: key is
  `SHA-256(api_key)[:8]:<source_ip>` — a fixed-length prefix of the key's hash
  concatenated with the source IP. The raw key value is never stored in limiter state.
- Source IP is extracted from the first hop of `X-Forwarded-For` when present, falling
  back to the ASGI `scope["client"][0]`.

#### Scenario: Same IP, same key — shared bucket
- **WHEN** two requests arrive from the same source IP with the same API key
- **THEN** they share the same rate-limit bucket

#### Scenario: Same IP, different keys — separate buckets
- **WHEN** two requests arrive from the same source IP with different API keys
- **THEN** they use separate rate-limit buckets

#### Scenario: No API key — IP-only bucket
- **WHEN** a request arrives with no `Authorization` header
- **THEN** the bucket key is the source IP alone

### Requirement: Per-endpoint default limits

The transport SHALL enforce the following default limits:

| Endpoint                   | Default limit      |
|----------------------------|--------------------|
| `GET /login`               | 30 req / 60 s      |
| `POST /login`              | 5 req / 300 s      |
| `/files/*`                 | 60 req / 60 s      |
| `/crews/{id}/api/*`        | 120 req / 60 s     |
| `/mcp` (and sub-paths)     | 300 req / 60 s     |

Each limit is independently overridable via environment variable (see next requirement).
`/crews/{id}/ui/*` (the browser-asset proxy) is not limited in this version — deferred
to a follow-on.

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

The transport SHALL read the following environment variables at startup to override
default limits. Each variable uses the format `<count>:<window_secs>` (both positive
integers). On parse failure the default is used and a `WARNING`-level log entry is
emitted naming the variable and describing the parse error. A master switch disables
the entire middleware.

| Variable                    | Controls                   |
|-----------------------------|----------------------------|
| `GA_RATE_LIMIT_ENABLED`     | Master switch (`true`/`false`, default `true`) |
| `GA_RATE_LIMIT_LOGIN_GET`   | `GET /login` limit         |
| `GA_RATE_LIMIT_LOGIN_POST`  | `POST /login` limit        |
| `GA_RATE_LIMIT_MCP`         | `/mcp` limit               |
| `GA_RATE_LIMIT_FILES`       | `/files/*` limit           |
| `GA_RATE_LIMIT_CREW_API`    | `/crews/*/api/*` limit     |

#### Scenario: Valid override is applied
- **WHEN** `GA_RATE_LIMIT_MCP=600:120` is set
- **THEN** the `/mcp` limiter allows 600 requests per 120-second window

#### Scenario: Malformed override falls back to default with a warning
- **WHEN** `GA_RATE_LIMIT_FILES=notanumber` is set
- **THEN** the `/files/*` limiter uses the default (60 req / 60 s) and a `WARNING` log
  entry names `GA_RATE_LIMIT_FILES` and describes the parse failure

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
