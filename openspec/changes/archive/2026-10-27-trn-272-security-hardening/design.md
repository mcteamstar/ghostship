# Design: TRN-272 — Security Hardening

## H-1: Per-session CSRF token

**Current state:** `_gs_sessions` holds the session store; `_dashboard_csrf_token` is a
single process-level token in `DashboardApp.__init__`.

**Approach:** Move the CSRF token into the session itself. On `GET /` (login page),
generate a per-request CSRF nonce (`secrets.token_hex(32)`); store it in a short-lived
pending map keyed by a one-time cookie. On `POST /login`, look up the nonce from that
cookie, compare, then discard.

Simpler alternative: issue the CSRF token as a cookie (SameSite=Strict, HttpOnly=False)
and require it echoed in the form. This avoids a server-side map but still ties the
token to the browser session, not the process.

**Decision:** Use the cookie-echo approach — stateless server side, sufficient protection
for the login form which is the only CSRF-exposed surface.

## H-2: XFF rate-limit proxy allowlist

**Current state:** `_caller_key()` reads `X-Forwarded-For` unconditionally.

**Approach:** Add `GA_TRUSTED_PROXY_CIDR` (default: empty). Parse as a comma-separated
list of CIDR strings at startup. In `_caller_key()`, if the ASGI client IP falls within
a trusted CIDR, use the first hop of XFF; otherwise use ASGI client IP.

When `GA_TRUSTED_PROXY_CIDR` is empty (default), XFF is never trusted — safe for
loopback-only and direct deployments. Operators behind a load balancer or Caddy on a
different host set the CIDR explicitly.

## H-8: Login flow TOCTOU

**Current state:** `LoginFlow` has a `_lock: asyncio.Lock`. `initiate()`, `abort()`, and
`is_expired()` are defined on the ABC but the login POST handlers in `login.py` read
`KIRO_FLOW.state` *outside* the lock.

**Approach:** Expose a context manager on `LoginFlow` (or use `async with flow._lock:`
directly in the POST handlers) that atomically reads state and pins `pending["container"]`
into a local variable within the lock. The critical section is short (a dict read), so
lock contention is negligible.

## L-1: Unicode normalisation in open-redirect guard

Normalise the `next` URL with `unicodedata.normalize("NFKC", url)` before passing to
`urlsplit`. This collapses lookalike sequences before path comparison.

## L-2: Secure flag on session cookie

Read `GA_EXTERNAL_URL` from config at cookie issuance time. Set `Secure=True` if scheme
is `https`. No new config key needed.

## L-5: `GA_BATCH_MAX_TASKS` parse

Wrap the `int()` call in config loading with `try/except ValueError` and raise
`ConfigError("GA_BATCH_MAX_TASKS must be an integer, got: ...")`.
