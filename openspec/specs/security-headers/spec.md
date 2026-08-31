# security-headers Specification

## Purpose

Defines transport-level HTTP security behaviors enforced by `SecurityHeadersMiddleware`. Currently scoped to the enforced-HTTPS redirect and the query-string sanitisation applied to it; baseline security headers (HSTS, CSP, clickjacking protection) are implemented but not yet covered by this capability's requirements.

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
