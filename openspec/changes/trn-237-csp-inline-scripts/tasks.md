# Tasks

## 1. Nonce generation and injection

- [ ] 1.1 In `transport/dashboard.py`, at the top of `handle_login_get`, add `import secrets` (or use the existing import if present) and generate a nonce: `nonce = secrets.token_urlsafe(16)`. Add `nonce="{nonce}"` to the `<style>` opening tag and `nonce="{nonce}"` to the `<script>` opening tag in the f-string. Verify: the rendered HTML contains `<style nonce="...">` and `<script nonce="...">` with the same value.

## 2. Custom CSP header on the login response

- [ ] 2.1 Replace the final `return Response(content=html, media_type="text/html; charset=utf-8")` with a response that includes a `Content-Security-Policy` header containing the nonce:
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
  The SecurityMiddleware skips injecting `DEFAULT_CSP` when the header is already present (`if name not in present` check in `transport/auth.py`). Verify: `GET /dashboard/login` response has a `Content-Security-Policy` header containing `nonce-` and the nonce value matches what appears in the HTML tags.

## 3. Tests

- [ ] 3.1 Add a test in `tests/unit/` (new file `test_trn237_login_csp.py` or add to an existing dashboard test file if one exists) covering:
  - `GET /dashboard/login` returns 200
  - Response has a `Content-Security-Policy` header
  - The CSP contains `'nonce-` followed by a non-empty value
  - The HTML body contains `<style nonce="` and `<script nonce="`
  - The nonce in the CSP header matches the nonce in both tags
  - A second request generates a different nonce (randomness check)
  Run `pytest tests/unit/ -q` and confirm green.

## 4. Spec delta

- [ ] 4.1 Write `openspec/changes/trn-237-csp-inline-scripts/specs/dashboard-security/spec.md`. Add requirement: the login page response must include a `Content-Security-Policy` header with a per-request nonce; inline scripts and styles must carry that nonce; `DEFAULT_CSP` must be unchanged and applied to all other routes.

## Workflow follow-up

- Archive the change after review.
