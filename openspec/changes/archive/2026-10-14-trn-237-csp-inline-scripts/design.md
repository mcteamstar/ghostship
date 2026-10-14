# Design

## Context

See proposal.md. Production enforces `Content-Security-Policy: default-src 'self'; frame-ancestors 'none'; object-src 'none'` (`DEFAULT_CSP` in `transport/security.py`, emitted enforced because `transport/server.py` passes `csp_enforce=True`). `default-src 'self'` disallows inline scripts/styles, which breaks the inline-only login page in `transport/dashboard.py` (`DashboardGate.handle_login_get`). The inline code is first-party and legitimate; the goal is to permit exactly those blocks without widening the policy.

## Goals

- Allow the login page's first-party inline `<script>` and `<style>` to run under the enforced CSP.
- Keep the policy strict: no `'unsafe-inline'`, no `'unsafe-eval'`; an injected inline block still cannot execute.
- Thread a per-request, single-use nonce from the middleware to the HTML generator without logging or reusing it.

## Non-Goals

- Moving the login page's CSS/JS to external `/static` files (a larger refactor; the nonce approach keeps the single-file, no-external-dependency property the login page was built with).
- Changing `default-src`, `frame-ancestors`, or `object-src`.
- Applying nonces to any surface other than the pages this transport generates server-side (the SPA served behind the gate is out of scope for this change).
- Adding a CSP violation `report-uri`/`report-to` endpoint.

## Decisions

### D1 — Per-request nonce, not `'unsafe-inline'`

Allowing inline code via `'unsafe-inline'` would defeat the CSP: any injected `<script>` would then execute. Instead, emit a per-request nonce and reference it in `script-src`/`style-src`. Only tags carrying the exact `nonce` attribute for that response run; an attacker cannot guess the nonce, so injected inline markup stays inert.

The nonce is generated with `secrets.token_urlsafe(16)` (128 bits of CSPRNG entropy, URL-safe base64 — valid verbatim in a CSP `'nonce-...'` source and in an HTML `nonce="..."` attribute). A fresh value is generated for every request; it is never persisted, never logged, and never reused across responses.

### D2 — Carry the nonce in the ASGI `scope`

The middleware runs outside the application and the dashboard handler runs inside it, so the nonce must cross that boundary. The middleware writes it to `scope["csp_nonce"]` before calling `self.app`, and the handler reads `request.scope.get("csp_nonce")`. The `scope` dict is per-request and never shared across requests, so there is no cross-request leakage. When no middleware ran (unit tests exercising the handler directly, `GA_ENABLE_SECURITY_HEADERS` off), the handler sees `None` and omits the attribute — the page still works in those non-enforcing contexts.

```python
# transport/auth.py — SecurityHeadersMiddleware.__call__
nonce = _security.generate_csp_nonce()
scope["csp_nonce"] = nonce
extra = _security.security_headers(
    https=https,
    csp_report_only=not self._csp_enforce,
    nonce=nonce,
)
# ... then: await self.app(scope, receive, send_wrapper)
```

### D3 — CSP string construction

`security_headers()` gains an optional `nonce` parameter. When present, the emitted CSP adds explicit `script-src` and `style-src` directives naming `'self'` and the nonce; `default-src 'self'` remains the fallback for every other fetch directive. When `nonce` is `None`, the policy is unchanged from today (preserving existing behaviour and tests that call `security_headers()` with no nonce).

```python
# transport/security.py
import secrets

def generate_csp_nonce() -> str:
    """Return a fresh 128-bit URL-safe nonce for a single response."""
    return secrets.token_urlsafe(16)

DEFAULT_CSP = "default-src 'self'; frame-ancestors 'none'; object-src 'none'"

def _csp_with_nonce(nonce: str) -> str:
    return (
        f"default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}'; "
        f"style-src 'self' 'nonce-{nonce}'; "
        f"frame-ancestors 'none'; object-src 'none'"
    )
```

The CSP value is still encoded `latin-1` for the ASGI header; the nonce alphabet (URL-safe base64) is a strict subset of latin-1, so encoding cannot fail.

### D4 — Stamp the nonce onto the login page's inline tags

`handle_login_get` reads the nonce once and interpolates it into the opening `<style>` and `<script>` tags. The nonce is a server-generated CSPRNG token (not user input), so it needs no HTML-attribute escaping, but it is placed only inside a double-quoted attribute to be defensive.

```python
# transport/dashboard.py — handle_login_get
nonce = request.scope.get("csp_nonce")
nonce_attr = f' nonce="{nonce}"' if nonce else ""
# ... <style{nonce_attr}> ... and <script{nonce_attr}> ...
```

**Alt considered:** externalise the CSS/JS into static assets served from `'self'`. Rejected for this change — it is a broader refactor, loses the login page's deliberate self-contained/no-external-dependency property, and still would not cover any future server-generated inline needs. The nonce path is the smaller, targeted fix and is the standard CSP mechanism for legitimate inline code.

### D5 — Preserve the report-only / enforce split

The nonce is independent of `csp_report_only`. In report-only mode (staged rollout / default) the same nonce-bearing policy is emitted under `content-security-policy-report-only`; in enforce mode (production) under `content-security-policy`. This keeps the two modes semantically identical apart from the header name, so violations observed in report-only accurately predict enforce behaviour.
