# Design

## Context

See proposal.md. The login page has inline `<style>` and `<script>` blocks that are blocked by the enforced `DEFAULT_CSP`. Fix: per-request nonce.

## Existing code (relevant)

`transport/dashboard.py handle_login_get` (~line 283):
- Generates the HTML as an f-string with `<style>` and `<script>` blocks
- Returns `Response(content=html, media_type="text/html; charset=utf-8")` with no custom headers

`transport/auth.py` SecurityMiddleware (~line 766):
- Appends `DEFAULT_CSP` as `Content-Security-Policy` to every response that doesn't already have that header
- Key: `if name not in present` — so setting the header on the response before the middleware runs will suppress the default

`transport/security.py`:
- `DEFAULT_CSP = "default-src 'self'; frame-ancestors 'none'; object-src 'none'"`
- Unchanged by this fix

## Decision

### D1 — Nonce generation

```python
import secrets
nonce = secrets.token_urlsafe(16)  # 128 bits, URL-safe base64, no padding issues
```

Generated once per request inside `handle_login_get`. Not stored — each page load gets a fresh nonce.

### D2 — Tag injection

Add `nonce="{nonce}"` attribute to both the `<style>` and `<script>` opening tags in the f-string:

```html
<style nonce="{nonce}">
  ...
</style>
...
<script nonce="{nonce}">
  ...
</script>
```

### D3 — Custom CSP header on the response

The login page needs `script-src` and `style-src` to allow the nonce. Rather than modifying `DEFAULT_CSP`, set a custom header on the login response directly. The SecurityMiddleware skips adding `Content-Security-Policy` if it's already present (`if name not in present`), so this naturally overrides:

```python
login_csp = (
    f"default-src 'self'; "
    f"script-src 'nonce-{nonce}'; "
    f"style-src 'nonce-{nonce}'; "
    f"frame-ancestors 'none'; "
    f"object-src 'none'"
)
return Response(
    content=html,
    media_type="text/html; charset=utf-8",
    headers={"Content-Security-Policy": login_csp},
)
```

`script-src` and `style-src` override `default-src` for those resource types. All other types (`img-src`, `connect-src`, etc.) fall through to `default-src 'self'`.

### D4 — No changes needed elsewhere

- `DEFAULT_CSP` stays unchanged — other routes are unaffected
- `security_headers()` stays unchanged
- The SecurityMiddleware's header-presence check handles the suppression automatically
