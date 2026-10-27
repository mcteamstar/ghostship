# TRN-272: Security Hardening

## Why

Independent review (indy-0.9.0, review ID 016025f5038b) identified multiple security
issues across the transport. Highest priority before any non-loopback deployment.

## What Changes

### H-1: Static per-process CSRF token (`transport/dashboard.py:99`)
`_csrf_token` is generated once at startup and shared across all users/sessions/tabs.
Fix: generate a fresh per-session CSRF token bound to the session; rotate on issuance.

### H-2: X-Forwarded-For trusted without proxy allowlisting (`transport/auth.py`)
`RateLimitMiddleware._caller_key()` reads XFF without restricting to trusted proxies —
clients can spoof XFF to bypass rate limits.
Fix: accept XFF only from a configured trusted-proxy CIDR; fall back to ASGI client IP.

### H-8: TOCTOU on login flow pending state (`transport/login.py`)
Login POST handlers read `FLOW.state` without the flow's lock, then dereference
`pending["container"]` seconds later. A concurrent `abort()` can cause a 500 or exec
into the wrong container. Affects lines ~936/946 (Kiro), ~1073–1078 (Claude), similarly
for Codex.
Fix: hold the flow lock across the state-read and container-dereference.

### H-9: `nuke()` not wrapped by `@_registry_guard` (`transport/tools.py:1129`)
A `RegistryCorruptError` propagates as an unhandled exception instead of `{"error": ...}`.
Fix: add `@_registry_guard` to `nuke()`.

### L-1: Open-redirect guard does not block Unicode normalisation attacks
`_validate_next_url()` in `dashboard.py` — Unicode lookalike paths can bypass.
Fix: normalise the URL before validation.

### L-2: Session cookie missing `Secure` flag when TLS is off and host is non-loopback
Fix: set `Secure` flag when the configured external URL uses `https://`.

### L-5: `GA_BATCH_MAX_TASKS` parse raises unhandled `ValueError` on non-integer input
Fix: catch and raise `ConfigError` with a clear message.

## Impact

- `transport/dashboard.py` — CSRF token, open-redirect normalisation, Secure flag
- `transport/auth.py` — XFF proxy allowlist
- `transport/login.py` — flow lock TOCTOU (Kiro, Claude, Codex paths)
- `transport/tools.py` — `@_registry_guard` on `nuke()`
- `transport/config.py` — `GA_TRUSTED_PROXY_CIDR` config key (new, optional)
