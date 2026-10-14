# Tasks

## 1. Nonce generation and nonce-aware CSP (`transport/security.py`)

- [x] 1.1 Add a `generate_csp_nonce() -> str` helper that returns a fresh URL-safe CSPRNG token with at least 128 bits of entropy (e.g. `secrets.token_urlsafe(16)`). `import secrets` at module top. Verify: a unit test confirms two calls return different values and the alphabet is URL-safe base64 (so it is valid both in a CSP `'nonce-...'` source and an HTML `nonce="..."` attribute).
- [x] 1.2 Extend `security_headers(...)` with an optional `nonce: str | None = None` parameter. When `nonce` is provided, build the CSP as `default-src 'self'; script-src 'self' 'nonce-<nonce>'; style-src 'self' 'nonce-<nonce>'; frame-ancestors 'none'; object-src 'none'`. When `nonce` is `None`, emit the existing `DEFAULT_CSP` unchanged. Do NOT add `'unsafe-inline'` or `'unsafe-eval'` in either case. Keep the `latin-1` header encoding. Verify: existing `test_security.py` CSP tests still pass; a new test asserts the nonce'd policy contains `script-src`/`style-src` with the nonce and omits `'unsafe-inline'`/`'unsafe-eval'`.

## 2. Middleware threads the nonce (`transport/auth.py`)

- [x] 2.1 In `SecurityHeadersMiddleware.__call__`, after the HTTPS/redirect handling and the `enable_headers` guard, generate a per-request nonce via `_security.generate_csp_nonce()`, store it in `scope["csp_nonce"]` before building headers, and pass it to `_security.security_headers(https=..., csp_report_only=not self._csp_enforce, nonce=nonce)`. Ensure the nonce is placed in `scope` BEFORE `await self.app(scope, receive, send_wrapper)` so downstream handlers can read it. Do not log the nonce. Verify: a unit test driving the middleware asserts the response CSP header contains a `'nonce-...'` value and that the same value is readable from `scope["csp_nonce"]`.
- [x] 2.2 Confirm the nonce is unique per request: add/extend a middleware unit test that sends two requests through the middleware and asserts the two CSP nonces differ. Run `tests/run.sh --unit` and confirm pass.

## 3. Stamp the nonce onto the login page (`transport/dashboard.py`)

- [x] 3.1 In `DashboardGate.handle_login_get`, read `nonce = request.scope.get("csp_nonce")` and build `nonce_attr = f' nonce="{nonce}"' if nonce else ""`. Apply `nonce_attr` to the opening `<style>` tag and the opening `<script>` tag in the login HTML (i.e. `<style{nonce_attr}>` and `<script{nonce_attr}>`). Do not otherwise change the inline CSS/JS. Verify: inspect the rendered HTML for a request carrying a scope nonce and confirm both tags gain the attribute.
- [x] 3.2 Add a dashboard unit test (co-located with the existing dashboard/security tests) that invokes `handle_login_get` with a request whose `scope` includes `csp_nonce`, and asserts the returned HTML's `<style>` and `<script>` tags both contain `nonce="<that value>"`. Add a second case with no `csp_nonce` in scope and assert the tags are emitted WITHOUT a `nonce` attribute and the page still returns 200 `text/html`. Run `tests/run.sh --unit` and confirm pass.

## 4. End-to-end CSP consistency check

- [x] 4.1 Add (or extend) a test that exercises the production wiring path — `SecurityHeadersMiddleware(..., csp_enforce=True)` wrapping the login route — and asserts the login response carries an enforced `content-security-policy` header whose `script-src`/`style-src` nonce matches the `nonce="..."` attribute on the HTML's inline `<script>`/`<style>` tags. This proves the browser would execute the first-party inline code under enforcement. Verify by running the test.
- [x] 4.2 Run the full unit suite (`tests/run.sh --unit`) and the security scan (`tests/security_scan.py`, if part of the gate) to confirm no regressions and that the enforced policy still contains neither `'unsafe-inline'` nor `'unsafe-eval'`.

## Workflow follow-up

- Hand off to Banshee for review once implementation and tests pass.
- Archive the change after review.
