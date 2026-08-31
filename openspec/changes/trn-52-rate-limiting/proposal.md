## Why

The ghostship transport has no general rate limiting. An unauthenticated or authenticated client can hammer any endpoint — `/mcp`, `/files/*`, `/crews/{id}/api/` — without restriction. `POST /login` has a brute-force throttle (5 failures / 15-min window via `Throttle` in `security.py`), but all other endpoints are unbounded. File endpoints can trigger large I/O and git bundle operations; `/mcp` can trigger container spawns and nuke operations.

## What Changes

- Add per-IP (or per-key when `GA_API_KEY` is set) rate limiting to the expensive unprotected endpoints
- Extend or reuse the existing `Throttle` class in `security.py`, or add a new token-bucket/sliding-window limiter
- Implement as Starlette middleware consistent with the existing `BearerAuthMiddleware` pattern
- Priority endpoints: `/files/*`, `/mcp`, `/crews/{id}/api/`, `GET /login`
- Proxy routes (`/crews/{id}/ui/`) and low-cost endpoints (`POST /logout`) are lower priority — defer or handle separately

## Capabilities

### New Capabilities

- `rate-limiting`: Per-endpoint rate limiting middleware — limits, keying strategy, and 429 response contract

### Modified Capabilities

- `installation`: Any new `GA_RATE_LIMIT_*` config vars need documenting in `docs/configuration.md` and `config/ghostship.conf.example`

## Impact

- `transport/security.py` — new or extended rate limiter class
- `transport/server.py` — middleware wiring
- `docs/configuration.md`, `config/ghostship.conf.example` — new env vars
- No transport API breaking changes; 429 responses are new but additive

## Open Questions

<!-- To be answered during design -->
- What are the right limits per endpoint? (`/files/*` and `/mcp` likely need different thresholds)
- Token bucket or sliding window? (Throttle class uses sliding window — extend or replace?)
- Key on source IP only, or also on API key (if set)?
- Should limits be configurable via env vars, or hardcoded sensible defaults?
- How does this interact with the proxy routes — does the limiter apply before or after the proxy decision?
