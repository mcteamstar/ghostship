# Proposal

**Plane ticket:** TRN-237

## Why

The transport now enforces its Content-Security-Policy unconditionally in production: `transport/server.py` wraps the app in `SecurityHeadersMiddleware(..., csp_enforce=True)`, so `transport/security.py` emits an **enforced** `Content-Security-Policy: default-src 'self'; frame-ancestors 'none'; object-src 'none'` on every response.

That policy has no `script-src`/`style-src` of its own, so `default-src 'self'` governs scripts and styles — and `'self'` does **not** permit inline `<script>` or `<style>` blocks. But the dashboard login page served by `DashboardGate.handle_login_get` (`transport/dashboard.py`) is built entirely from inline CSS and an inline script (password show/hide toggle, failure-shake animation, and the `fetch`-based form submit that honours the server-sanitised `next` URL). Under the enforced CSP a conforming browser **refuses to execute that inline script and refuses to apply the inline styles**, so the login page renders unstyled and its sign-in button does nothing — the dashboard is unreachable.

This is a correctness regression introduced by flipping CSP from report-only to enforce. The inline code is legitimate first-party code, so the right fix is to allow it explicitly and narrowly — not to weaken the policy to `'unsafe-inline'`, which would re-open the XSS surface the CSP exists to close.

## What Changes

- **Per-request CSP nonce.** `SecurityHeadersMiddleware` generates a fresh cryptographically-random nonce per request, injects `script-src 'self' 'nonce-<nonce>'` and `style-src 'self' 'nonce-<nonce>'` into the emitted CSP, and makes the nonce available to downstream handlers (via the ASGI `scope`) so the HTML generator can stamp it onto its inline tags.
- **Nonce-stamped inline tags.** `DashboardGate.handle_login_get` reads the per-request nonce and emits `<script nonce="...">` and `<style nonce="...">` so the browser executes/applies exactly those first-party blocks and nothing else.
- **Policy stays strict.** `'unsafe-inline'` and `'unsafe-eval'` are **not** added. `default-src 'self'`, `frame-ancestors 'none'`, and `object-src 'none'` are preserved. Any inline block without the matching nonce remains blocked, so an injected `<script>` still cannot run.
- **No nonce leakage.** The nonce is single-use per response, never logged, never reused across requests, and generated from a CSPRNG.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `security-headers`: add requirements for a per-request CSP nonce, nonce-aware `script-src`/`style-src` directives, preservation of the strict base policy (no `'unsafe-inline'`/`'unsafe-eval'`), and nonce exposure to downstream handlers.

## Impact

- `transport/security.py` — `security_headers()` / `DEFAULT_CSP`: accept a per-request nonce and emit `script-src`/`style-src` with `'nonce-<nonce>'`; add a nonce generator helper.
- `transport/auth.py` — `SecurityHeadersMiddleware.__call__`: generate a nonce per request, place it in the ASGI `scope`, and pass it to `security_headers()`.
- `transport/dashboard.py` — `DashboardGate.handle_login_get`: read the scope nonce and stamp it onto the inline `<style>` and `<script>` tags.
- Tests: `tests/unit/test_security.py` — nonce presence/format/uniqueness in the CSP, `script-src`/`style-src` directives, absence of `'unsafe-inline'`; and a dashboard test asserting the login HTML's inline tags carry the request nonce.
