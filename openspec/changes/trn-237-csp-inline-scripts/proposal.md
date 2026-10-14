# Proposal

**Plane ticket:** TRN-237

## Why

`DEFAULT_CSP = "default-src 'self'; frame-ancestors 'none'; object-src 'none'"` is applied to all responses including the dashboard login page. `'self'` does not allow inline scripts or styles under CSP Level 2+, and `server.py` passes `csp_enforce=True` — so enforcement is active. The login page (`transport/dashboard.py handle_login_get`) has both an inline `<style>` block and an inline `<script>` block. Both are silently blocked by the enforced CSP in compliant browsers, breaking the login UX entirely.

## What Changes

- `handle_login_get` generates a cryptographically random per-request nonce (`secrets.token_urlsafe(16)`)
- The nonce is injected as `nonce="<value>"` on both the `<style>` and `<script>` tags
- The response is returned with a custom `Content-Security-Policy` header that adds `'nonce-<value>'` to `script-src` and `style-src` (falling back to `default-src`)
- `DEFAULT_CSP` is unchanged — all other routes continue using it as before
- No external files needed; the login page stays self-contained

## Approach

Nonce-based allowlisting is the correct fix. Alternatives rejected:
- `'unsafe-inline'` — defeats the CSP entirely, wrong direction
- External JS/CSS files — unnecessary complexity for a single self-contained page
- `'unsafe-hashes'` — hash must be recomputed whenever the script changes; nonce is simpler and equally secure

## Capabilities

### Modified Capabilities

- `dashboard-security`: login page CSP now permits its own inline scripts and styles via per-request nonce; enforcement remains active for all other content

## Impact

- `transport/dashboard.py` — `handle_login_get`: nonce generation, tag injection, custom CSP header on response
- `transport/security.py` — no changes to `DEFAULT_CSP` or `security_headers`
- `tests/unit/` — new test for nonce presence and CSP header on `GET /dashboard/login`
