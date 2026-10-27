# TRN-272: Security Hardening

## Why

Independent review (indy-0.9.0, review ID 016025f5038b) identified security issues in
the transport. All are verified against the actual source. Highest priority before any
non-loopback deployment.

Source verified: H-9 (`nuke()` missing `@_registry_guard`) was a false positive — the
decorator is present at `tools.py:1149`. Removed from scope.

## What Changes

### H-1: Static per-process CSRF token (`transport/dashboard.py:99`)
`_csrf_token` is generated once at startup and shared across all sessions and tabs.
Confirmed: `self._csrf_token: str = secrets.token_hex(32)` on line 99; used in form
at line 294 and validated at lines 158 and 263.
Fix: generate a fresh per-session CSRF token stored in the session; rotate on issuance.

### H-2: X-Forwarded-For trusted without proxy allowlisting (`transport/auth.py:244`)
`RateLimitMiddleware._caller_key()` reads XFF first hop without restricting to trusted
proxies — clients behind any proxy can spoof XFF to bypass rate limits.
Confirmed: line 245 comment reads "X-Forwarded-For first hop, else ASGI client".
Fix: accept XFF only when client IP is in a configured `GA_TRUSTED_PROXY_CIDR`; fall
back to ASGI client IP otherwise. Default: no trusted proxies (safe for loopback-only).

### H-8: TOCTOU on login flow pending state (`transport/login.py:936/946`)
Kiro POST handler reads `KIRO_FLOW.state` at line 900/936 without holding the flow's
lock, then dereferences `pending["container"]` at line 946 seconds later. A concurrent
`abort()` in another request can race and clear the state between these two reads,
causing a 500 or read of a stale container. Same pattern at Claude (~1073/1078) and
Codex.
Fix: hold the flow lock across the state snapshot and container dereference.

### L-1: Open-redirect guard does not block Unicode normalisation attacks
`_validate_next_url()` in `dashboard.py` can be bypassed with Unicode lookalike paths.
Fix: NFKC-normalise the URL string before validation.

### L-2: Session cookie missing `Secure` flag when TLS is off and host is non-loopback
Fix: set `Secure` flag when the transport's external URL scheme is `https://`.

### L-5: `GA_BATCH_MAX_TASKS` parse raises unhandled `ValueError` on non-integer input
Fix: catch `ValueError` in env parse and raise `ConfigError` with a clear message.

## What does NOT change

- `nuke()` `@_registry_guard` — already present at `tools.py:1149` (false positive from
  review; no action needed)

## Impact

- `transport/dashboard.py` — per-session CSRF token, open-redirect normalisation, Secure flag
- `transport/auth.py` — `_caller_key()` XFF proxy allowlist
- `transport/login.py` — flow lock TOCTOU (Kiro, Claude, Codex paths)
- `transport/config.py` — `GA_TRUSTED_PROXY_CIDR` config key (new, optional, default empty)
