# security-headers Specification

## Purpose

Defines transport-level HTTP security behaviors enforced by `SecurityHeadersMiddleware`. Covers the enforced-HTTPS redirect and its query-string sanitisation, and the per-request nonce-based Content-Security-Policy that admits first-party inline `<script>`/`<style>` while keeping the strict base policy. Other baseline security headers (HSTS, clickjacking protection) are implemented but not yet covered by this capability's requirements.

## Requirements

### Requirement: Plaintext HTTP redirects to HTTPS with a sanitised query string

When `GA_ENFORCE_HTTPS_REDIRECT` is enabled and a request arrives over plaintext HTTP (not `/health`), the transport SHALL respond with a 301 redirect to the HTTPS equivalent of the request. The redirect target's query string SHALL be built using the same sanitisation applied to the crew reverse-proxy handlers: raw ASCII control bytes (`0x00`–`0x1F` and `0x7F`) SHALL be removed before the query string is appended to the `Location` header, preventing CRLF injection into the redirect response. Percent-encoded query text SHALL NOT be decoded or altered by this sanitisation.

#### Scenario: Redirect strips raw control bytes from the query string
- **WHEN** a plaintext HTTP request with `GA_ENFORCE_HTTPS_REDIRECT` enabled contains raw query-string bytes `q=hello\r\nworld\x00&limit=10`
- **THEN** the 301 response's `Location` header contains `q=helloworld&limit=10` and no raw byte in `0x00`–`0x1F` or `0x7F`

#### Scenario: Redirect preserves ordinary and percent-encoded query text
- **WHEN** a plaintext HTTP request with `GA_ENFORCE_HTTPS_REDIRECT` enabled contains the query string `q=hello%0Aworld&limit=10`
- **THEN** the 301 response's `Location` header query string is exactly `q=hello%0Aworld&limit=10`

#### Scenario: Health probe is exempt from the redirect
- **WHEN** a plaintext HTTP request to `/health` arrives with `GA_ENFORCE_HTTPS_REDIRECT` enabled
- **THEN** the transport does not redirect and serves the health check directly

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
