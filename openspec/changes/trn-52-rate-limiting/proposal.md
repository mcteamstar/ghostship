## Why

The transport currently has no per-endpoint request rate limiting. A single API key holder
(or an unauthenticated caller when `GA_API_KEY` is unset) can flood any endpoint without
penalty. The highest-value attack surfaces are:

- `/files/*` — expensive presigned-URL operations backed by git subprocess execution
- `/mcp` — the MCP streamable-HTTP endpoint that drives all crew orchestration tools
- `/crews/{id}/api/` — passes requests through to the per-crew gateway
- `GET /login` — polling endpoint that must stay responsive during the device-auth flow

The existing `Throttle` class in `transport/security.py` handles brute-force login
throttling (keyed on account+source, sliding window). Rate limiting is a related but
distinct concern: it bounds the *request rate* for any caller regardless of failure
count, rather than locking out repeated auth failures. The two mechanisms complement
each other and should share the same sliding-window primitive.

## What Changes

- New `RateLimiter` class in `transport/security.py` — sliding-window, keyed on caller
  identity (see design.md), stdlib-only, thread-safe
- New `RateLimitMiddleware` ASGI middleware class in `transport/server.py` — applied after
  `SecurityHeadersMiddleware` and before `BearerAuthMiddleware`, so limits apply to all
  callers including unauthenticated ones hitting `/login`
- Per-endpoint limit table with env-var overrides for all four priority endpoints
- 429 Too Many Requests response with `Retry-After` header
- Proxy routes (`/crews/{id}/ui/`) noted as deferred — lower risk, addressed in a
  follow-on

## Capabilities

### New Capabilities

- `rate-limiting`: The `RateLimiter` primitive and `RateLimitMiddleware` ASGI layer —
  algorithm, keying strategy, per-endpoint limits, env-var configuration contract, and
  429 response shape.

### Modified Capabilities

- `installation`: Document the new rate-limiting env vars in `docs/configuration.md` and
  `config/ghostship.conf.example`.

## Open Questions

*(resolved in design.md)*

- Token bucket or sliding window?
- Key on source IP only, or also on API key when presented?
- What are sensible default limits per endpoint?
- Should limits be configurable via env vars?
- How does limiting interact with the proxy routes?

## Impact

- `transport/security.py` — new `RateLimiter` class (~60 lines)
- `transport/server.py` — new `RateLimitMiddleware` class + wiring (~50 lines)
- `docs/configuration.md` — new env vars section
- `config/ghostship.conf.example` — new commented-out rate-limit vars
- No new dependencies (stdlib only)
- No breaking changes to existing API surface
