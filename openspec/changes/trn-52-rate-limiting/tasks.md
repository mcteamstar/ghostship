# TRN-52 Tasks — HTTP Rate Limiting

## 1. Add `RateLimiter` to `transport/security.py`

- [ ] 1.1 Add a `RateLimiter` dataclass to `transport/security.py` immediately after the `Throttle` class. Fields: `max_requests: int`, `window_secs: float`, `_hits: dict[str, list[float]]` (default factory), `_lock: threading.Lock` (default factory). Use the same `_prune` sliding-window pattern as `Throttle`.
- [ ] 1.2 Implement `_prune(self, key, now)` — returns the pruned timestamp list for `key`, removing entries older than `window_secs`; removes the key entirely when the list is empty.
- [ ] 1.3 Implement `is_limited(self, key, now=None) -> bool` — returns `True` if the pruned hit count is `>= max_requests` (read-only, no recording).
- [ ] 1.4 Implement `record(self, key, now=None) -> bool` — atomically prunes, checks, and if within limit appends the timestamp and returns `True`; returns `False` without appending if already at the limit.
- [ ] 1.5 Run `python3 -m unittest discover -s transport -p "test_*.py" -q` — all existing tests pass.

## 2. Add `RateLimitMiddleware` to `transport/server.py`

- [ ] 2.1 Add a `RateLimitMiddleware` class in `transport/server.py` (place it near `BearerAuthMiddleware`, before it in the file). Constructor accepts `app`, `limiters: dict[str, RateLimiter]`, and `api_key: str = ""`.
- [ ] 2.2 Implement `_caller_key(scope, bearer_token)` as a method — extracts source IP from `X-Forwarded-For` (first hop) or `scope["client"][0]`; when `bearer_token` is provided, returns `SHA-256(bearer_token).hexdigest()[:8]:<source_ip>`; when absent returns the IP alone.
- [ ] 2.3 Implement `_match_endpoint(method, path) -> str | None` — returns the limiter key for the request or `None` for unmatched paths. Priority order: `"login_post"` (POST /login), `"login_get"` (GET /login), `"files"` (path.startswith("/files/")), `"crew_api"` (path matches `/crews/*/api/*` pattern), `"mcp"` (path startswith "/mcp").
- [ ] 2.4 Implement `__call__(scope, receive, send)` — passes through non-HTTP scopes and exempt paths (`/health`, `/version`); for rate-limited endpoints calls `limiter.record(caller_key)` and returns 429 with `Retry-After` header if denied; otherwise calls `await self.app(scope, receive, send)`.
- [ ] 2.5 Run existing tests — all pass.

## 3. Add env-var configuration and wiring in `main()`

- [ ] 3.1 Add `_parse_rate_limit_var(name, default_count, default_window)` helper function — reads `os.environ.get(name)`, parses `"count:window"` format, logs a `WARNING` (naming the variable) on parse failure, returns `(count, window)` tuple.
- [ ] 3.2 Add `_build_rate_limiters() -> dict[str, RateLimiter] | None` function — reads `GA_RATE_LIMIT_ENABLED` (default `"true"`); returns `None` if disabled; otherwise calls `_parse_rate_limit_var` for each of the five endpoints and returns a dict of `RateLimiter` instances keyed by endpoint name.
- [ ] 3.3 In `main()`, call `_build_rate_limiters()` after `BearerAuthMiddleware` is constructed. If the result is not `None`, wrap `app = RateLimitMiddleware(app, limiters=limiters, api_key=GA_API_KEY)`. Log an `INFO` entry confirming rate limiting is active (or disabled). Place this wrap **between** `SecurityHeadersMiddleware` wrapping and `BearerAuthMiddleware` construction so the final stack from outermost to innermost is: `SecurityHeadersMiddleware → RateLimitMiddleware → BearerAuthMiddleware → mcp_app`.
- [ ] 3.4 Run `python3 -m unittest discover -s transport -p "test_*.py" -q` — all existing tests pass.

## 4. Tests

- [ ] 4.1 Test `RateLimiter.record()` — allows requests up to `max_requests`, denies the next one; window slides correctly (old timestamps expire).
- [ ] 4.2 Test `RateLimiter` thread safety — concurrent `record()` calls from two threads at the boundary never exceed `max_requests`.
- [ ] 4.3 Test `RateLimitMiddleware` — request within limit passes to inner app (mock), receives inner app's response.
- [ ] 4.4 Test `RateLimitMiddleware` — request over limit returns 429 with `Retry-After` header; inner app is not called.
- [ ] 4.5 Test `/health` and `/version` are exempt — no limiter registered for them; requests always pass through regardless of call count.
- [ ] 4.6 Test `_parse_rate_limit_var` — valid `"60:60"` parses correctly; malformed input returns the default and logs a WARNING.
- [ ] 4.7 Test `GA_RATE_LIMIT_ENABLED=false` — `_build_rate_limiters()` returns `None`; middleware is not added to the stack in the resulting app.
- [ ] 4.8 Run `python3 -m unittest discover -s transport -p "test_*.py" -q` — all tests pass including the new ones.

## 5. Documentation

- [ ] 5.1 Add a "Rate Limiting" section to `docs/configuration.md` listing all six `GA_RATE_LIMIT_*` variables, their `<count>:<window_secs>` format, defaults, and the note that state resets on restart.
- [ ] 5.2 Add commented-out `GA_RATE_LIMIT_*` entries to `config/ghostship.conf.example`, each showing the default value and a brief inline comment.

## 6. Commit

- [ ] 6.1 Commit: `feat(trn-52): add HTTP rate limiting (RateLimiter + RateLimitMiddleware)`
