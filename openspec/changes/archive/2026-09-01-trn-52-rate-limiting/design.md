# TRN-52 Design — HTTP Rate Limiting

## Context

See `proposal.md` for motivation. The transport already has a `Throttle` class in
`transport/security.py` (sliding window, keyed on `account+source`, scoped to
failed-auth tracking). This change adds a complementary `RateLimiter` that bounds
*request rate* — not failure count — across all callers on the four priority endpoints.

The middleware stack order (outermost → innermost) will be:

```
SecurityHeadersMiddleware      — adds security headers, enforces HTTPS redirect
  RateLimitMiddleware          — NEW: per-endpoint rate limiting (this change)
    BearerAuthMiddleware       — API key auth, login/logout routing, file pass-through
      mcp_app                  — MCP streamable-HTTP handler
```

`RateLimitMiddleware` sits outside `BearerAuthMiddleware` so it catches all inbound
requests, including unauthenticated attempts to `/login` and any pre-auth probing.

---

## Decisions

### 1. Algorithm: sliding window (not token bucket)

**Decision:** sliding window, matching `Throttle`.

**Rationale:** The existing `Throttle` uses a sliding window — a list of timestamps
pruned to the last `window_secs`. `RateLimiter` uses the same structure so the two
share implementation pattern and are easy to reason about together. Token buckets
offer smoother burst absorption, but for a local single-user transport the difference
is negligible and consistency with existing code outweighs marginal burst-smoothing
benefit. Both are `O(n)` in the number of requests in the window, which is fine given
the low per-window counts (≤ 1000 requests in the largest window).

The implementation keeps the per-key timestamp list in memory (same as `Throttle`),
pruned on each check so the dict stays bounded. No external store is needed for
single-process local deployment.

### 2. Keying strategy: IP + API key composite

**Decision:** key on `source_ip` when no API key is present; key on `api_key_prefix`
alone when a valid API key is presented; key on the composite `api_key_prefix:source_ip`
when both are available.

**Rationale:**

- *IP-only* penalises legitimate users behind NAT sharing an IP, and offers no isolation
  when the key is known.
- *API-key-only* leaks: if there is only one key it gives a single global bucket
  shared by all processes using the same key (the common single-user case), which is
  actually the right behaviour — one key holder gets one quota.
- *Composite* (key + IP) is the best general choice: each distinct source IP on the
  same key gets its own limit. For the single-user case (one machine, one IP) this
  degenerates to the same bucket as key-only.
- When no API key is set (auth-disabled mode), IP is the only available signal.

Source IP extraction mirrors `_reject`'s existing pattern: first check
`X-Forwarded-For` (first hop), then fall back to the ASGI `scope["client"][0]`.

API key identity uses the first 8 hex chars of `SHA-256(key)` — enough to distinguish
keys without storing the key itself in the rate-limiter state. This is the same
defensive pattern used elsewhere in the codebase.

### 3. Default limits per endpoint

Limits are specified as `(max_requests, window_secs)` tuples.

| Endpoint pattern       | Default limit         | Rationale |
|------------------------|-----------------------|-----------|
| `GET /login`           | 30 req / 60 s         | Polling during device-auth; 30 req/min is generous for a human polling flow but blocks automated hammering |
| `POST /login`          | 5 req / 300 s         | One login attempt every minute is more than enough; 5 in 5 min prevents rapid retries |
| `/mcp`                 | 300 req / 60 s        | MCP tools are the primary work surface; 5 req/s gives headroom for multi-tool orchestration |
| `/files/*`             | 60 req / 60 s         | File operations involve git subprocess execution; 1/s sustained with burst room |
| `/crews/{id}/api/*`    | 120 req / 60 s        | Proxied crew API calls; 2/s gives room for rapid polling without unbounded fan-out |

All five limits are independently overridable via env vars (see §4). The
`/crews/{id}/ui/*` proxy is noted but deferred — it serves browser assets and
WebSocket upgrades whose request patterns differ from API traffic; the risk profile
is lower and the appropriate limit needs a separate investigation.

`/health` and `GET /version` are excluded from rate limiting — they are used by
health probes and must never 429.

### 4. Env var names and configuration

All vars follow the existing `GA_` prefix convention.

```
GA_RATE_LIMIT_LOGIN_GET=30:60        # max_requests:window_secs for GET /login
GA_RATE_LIMIT_LOGIN_POST=5:300       # max_requests:window_secs for POST /login
GA_RATE_LIMIT_MCP=300:60            # max_requests:window_secs for /mcp
GA_RATE_LIMIT_FILES=60:60           # max_requests:window_secs for /files/*
GA_RATE_LIMIT_CREW_API=120:60       # max_requests:window_secs for /crews/*/api/*
GA_RATE_LIMIT_ENABLED=true          # master switch; set to "false" to disable entirely
```

Format is `<count>:<window_secs>` (both integers). On parse failure the default is
used and a warning is logged (same pattern as other GA_ vars). `GA_RATE_LIMIT_ENABLED`
defaults to `true`; set `false` to disable the middleware entirely without code changes.

These vars are documented in `docs/configuration.md` and added as commented-out
entries in `config/ghostship.conf.example`.

### 5. 429 response shape

```
HTTP/1.1 429 Too Many Requests
Content-Type: text/plain; charset=utf-8
Retry-After: <window_secs>

Rate limit exceeded. Retry after <window_secs> seconds.
```

`Retry-After` is the full window duration (conservative). This is intentional — it
tells the client to back off for the full window rather than encouraging tight
retry loops near the boundary.

### 6. Proxy routes (`/crews/{id}/ui/`)

Deferred. The UI proxy serves browser assets (JS, CSS, WebSocket upgrades) whose
request patterns differ substantially from API/MCP traffic. Applying the same
fixed-count limit would either be too tight (breaking asset loading) or too loose
(not meaningfully protective). A dedicated follow-on ticket should profile normal
UI traffic and set an appropriate limit or use a token bucket for burst absorption.

The `/crews/{id}/api/*` proxy (crew API calls) is in scope and covered by
`GA_RATE_LIMIT_CREW_API`.

---

## Implementation sketch

### `transport/security.py` — `RateLimiter`

```python
@dataclass
class RateLimiter:
    """Sliding-window request-rate limiter keyed on arbitrary string keys.

    Shares the same sliding-window pattern as Throttle but tracks request
    *count* rather than failure count. Thread-safe; no external store needed.
    """
    max_requests: int
    window_secs: float
    _hits: dict[str, list[float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _prune(self, key: str, now: float) -> list[float]:
        stamps = [t for t in self._hits.get(key, []) if now - t < self.window_secs]
        if stamps:
            self._hits[key] = stamps
        else:
            self._hits.pop(key, None)
        return stamps

    def is_limited(self, key: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with self._lock:
            return len(self._prune(key, now)) >= self.max_requests

    def record(self, key: str, now: float | None = None) -> bool:
        """Record a request. Returns True if the request is allowed, False if limited."""
        now = time.time() if now is None else now
        with self._lock:
            stamps = self._prune(key, now)
            if len(stamps) >= self.max_requests:
                return False
            stamps.append(now)
            self._hits[key] = stamps
            return True
```

### `transport/server.py` — `RateLimitMiddleware`

```python
class RateLimitMiddleware:
    """ASGI middleware enforcing per-endpoint sliding-window rate limits.

    Applied outside BearerAuthMiddleware so all callers are subject to limits,
    including unauthenticated /login requests. Health and version endpoints
    are unconditionally exempt.
    """

    _EXEMPT: frozenset[str] = frozenset({"/health", "/version"})

    def __init__(self, app, *, limiters: dict[str, RateLimiter], api_key: str = "") -> None:
        self.app = app
        self._limiters = limiters   # pattern → RateLimiter; matched in registration order
        self._api_key = api_key

    def _caller_key(self, scope: dict, bearer_token: str | None) -> str:
        # Extract source IP (X-Forwarded-For first hop → ASGI client)
        source_ip = None
        for k, v in scope.get("headers", []):
            if k == b"x-forwarded-for":
                source_ip = v.decode("latin-1").split(",")[0].strip()
                break
        if source_ip is None:
            client = scope.get("client")
            source_ip = client[0] if client else "unknown"

        if not bearer_token:
            return source_ip
        # Hash the key to avoid storing it in limiter state
        import hashlib
        key_prefix = hashlib.sha256(bearer_token.encode()).hexdigest()[:8]
        return f"{key_prefix}:{source_ip}"

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path in self._EXEMPT:
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "")
        endpoint_key = self._match_endpoint(method, path)
        limiter = self._limiters.get(endpoint_key)
        if limiter is None:
            await self.app(scope, receive, send)
            return
        # Extract bearer token (best-effort — may be absent or invalid)
        bearer = None
        for k, v in scope.get("headers", []):
            if k == b"authorization":
                val = v.decode("latin-1")
                if val[:7].lower() == "bearer ":
                    bearer = val[7:].strip()
                break
        caller = self._caller_key(scope, bearer)
        if not limiter.record(caller):
            # 429
            retry_after = str(int(limiter.window_secs)).encode()
            await send({"type": "http.response.start", "status": 429,
                        "headers": [[b"content-type", b"text/plain; charset=utf-8"],
                                    [b"retry-after", retry_after]]})
            await send({"type": "http.response.body",
                        "body": b"Rate limit exceeded. Retry after " + retry_after + b" seconds."})
            return
        await self.app(scope, receive, send)
```

The `_match_endpoint` method returns a string key by testing the method+path against
the registered patterns in priority order:
1. `"login_post"` — `POST /login`
2. `"login_get"` — `GET /login`
3. `"files"` — path starts with `/files/`
4. `"crew_api"` — path matches `/crews/*/api/*`
5. `"mcp"` — path starts with `/mcp`

### Wiring in `main()`

```python
limiters = _build_rate_limiters()   # reads GA_RATE_LIMIT_* env vars
app = RateLimitMiddleware(app, limiters=limiters, api_key=GA_API_KEY)
```

Applied after `SecurityHeadersMiddleware` is wrapped around `BearerAuthMiddleware`,
so the final stack from outermost to innermost is:
`SecurityHeadersMiddleware → RateLimitMiddleware → BearerAuthMiddleware → mcp_app`.

---

## Risks and Trade-offs

- **In-memory state**: limits reset on process restart. Acceptable for a
  single-process local transport. Documented as a known property.
- **IP behind NAT**: multiple legitimate users sharing a NAT IP share a limit bucket.
  For the single-user local use case this is not a concern. The composite key
  partially mitigates it when a valid API key is also present.
- **No persistence**: a deliberate restart is an effective limit reset. Acceptable —
  the goal is protecting against runaway clients, not persistent rate enforcement.
- **Deferred proxy-UI limit**: `/crews/{id}/ui/` is unprotected for now. The
  rationale is documented in §6 and a follow-on ticket is the intended path.
