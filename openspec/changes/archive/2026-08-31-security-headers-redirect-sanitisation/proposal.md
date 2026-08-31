## Why

Commit `203c9f5` ("fix(trn-55): backport HTTPS redirect sink + precompiled pattern from crew") shipped directly to `release/0.2.2` without an OpenSpec change behind it. It extends TRN-55's query-string sanitisation (`_sanitise_query_string`, originally scoped to the two crew reverse-proxy handlers) to a second sink: `SecurityHeadersMiddleware`'s plaintext→HTTPS 301 redirect, which builds its `Location` header from the same raw, unsanitised query string. That sink carries the identical CRLF-injection risk TRN-55 fixed for the proxy handlers, just landing in a redirect header instead of a proxied upstream URL. No spec capability currently documents `SecurityHeadersMiddleware`'s behavior at all (it shipped under TRN-70 without one), so this fix has no paper trail. This change retroactively documents the already-shipped fix rather than proposing new work.

## What Changes

- Document `SecurityHeadersMiddleware`'s HTTPS-redirect behavior as a new capability, scoped to what's true today: the redirect itself and the query-string sanitisation applied to its `Location` header. (Its other responsibilities — baseline security headers, HSTS, CSP — are real but untouched by this fix and are left for a future change to document, rather than over-claiming coverage here.)
- No code changes — `transport/server.py`'s `SecurityHeadersMiddleware` already contains this behavior as of `203c9f5`.

## Capabilities

### New Capabilities
- `security-headers`: transport-level HTTP security behaviors — currently scoped to the enforced-HTTPS redirect and the query-string sanitisation applied to its `Location` header.

### Modified Capabilities
(none)

## Impact

- No code impact — this is a documentation-only change syncing the spec store with already-shipped behavior.
- `openspec/specs/security-headers/spec.md`: new capability spec.
