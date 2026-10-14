# Spec Delta

## ADDED Requirements

### Requirement: CSP carries a per-request nonce for first-party inline code
`SecurityHeadersMiddleware` SHALL generate a fresh cryptographically-random nonce for every HTTP request and emit a Content-Security-Policy whose `script-src` and `style-src` directives name both `'self'` and that request's nonce (`'nonce-<value>'`). The nonce SHALL be derived from a CSPRNG with at least 128 bits of entropy and SHALL be unique per response — never reused across requests and never persisted. The nonce value SHALL NOT be written to any log.

#### Scenario: Each response carries a unique script-src/style-src nonce
- **WHEN** two separate HTTP requests are served with security headers enabled
- **THEN** each response's `Content-Security-Policy` (or `Content-Security-Policy-Report-Only`) contains a `script-src` and a `style-src` directive with a `'nonce-...'` source, and the two responses' nonce values differ

#### Scenario: Nonce is a CSPRNG value, not a fixed or predictable string
- **WHEN** the middleware generates a CSP nonce
- **THEN** the nonce is produced from a cryptographically secure random source with at least 128 bits of entropy and is not a constant or request-derivable value

### Requirement: Nonce-aware CSP preserves the strict base policy
The nonce-bearing Content-Security-Policy SHALL retain `default-src 'self'`, `frame-ancestors 'none'`, and `object-src 'none'`, and SHALL NOT include `'unsafe-inline'` or `'unsafe-eval'` in any directive. An inline `<script>` or `<style>` without the matching per-request nonce SHALL remain blocked by the policy.

#### Scenario: Policy admits nonce'd inline code but still forbids unsafe-inline
- **WHEN** the middleware emits a CSP for a request
- **THEN** the policy string contains `'nonce-...'` in `script-src` and `style-src`, retains `default-src 'self'`, `frame-ancestors 'none'`, and `object-src 'none'`, and contains neither `'unsafe-inline'` nor `'unsafe-eval'`

#### Scenario: Base policy is unchanged when no nonce is supplied
- **WHEN** `security_headers()` is called without a nonce (report-only staged default or a caller that does not opt in)
- **THEN** the emitted policy equals the existing `default-src 'self'; frame-ancestors 'none'; object-src 'none'` with no `script-src`/`style-src` nonce directives added

### Requirement: Per-request nonce is exposed to downstream handlers
`SecurityHeadersMiddleware` SHALL place the request's generated nonce in the ASGI `scope` under a stable key before invoking the wrapped application, so a server-generated HTML response can stamp the same nonce onto its inline `<script>` and `<style>` tags. The nonce in the `scope` SHALL be the identical value referenced by that response's CSP header.

#### Scenario: Handler reads the same nonce that the CSP header carries
- **WHEN** a downstream handler is invoked for a request processed by the middleware
- **THEN** the handler can read the request's nonce from the ASGI `scope`, and that value is byte-for-byte the `'nonce-...'` value in the response's CSP header

### Requirement: Dashboard login page executes under the enforced CSP
The dashboard login page served by `DashboardGate.handle_login_get` SHALL stamp the request's CSP nonce onto its inline `<style>` and `<script>` tags so the page's styles apply and its script executes under the enforced Content-Security-Policy. When no nonce is present in the `scope` (security headers disabled, or the handler invoked outside the middleware), the page SHALL still render by omitting the nonce attribute.

#### Scenario: Login page inline tags carry the request nonce
- **WHEN** the login page is served for a request that carries a CSP nonce in its ASGI `scope`
- **THEN** the returned HTML's inline `<style>` and `<script>` tags each include a `nonce="<value>"` attribute equal to the request's nonce

#### Scenario: Login page still renders without a nonce
- **WHEN** the login page is served for a request with no CSP nonce in its `scope`
- **THEN** the returned HTML's inline `<style>` and `<script>` tags are emitted without a `nonce` attribute and the page is otherwise unchanged
