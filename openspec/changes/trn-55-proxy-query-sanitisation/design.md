## Context

The crew UI and REST API reverse-proxy handlers receive the ASGI query string as raw bytes and currently turn it into the upstream URL with a `latin-1` decode. That preserves raw ASCII control bytes, including carriage return and line feed, at the boundary where the URL is handed to the internal gateway client. See `proposal.md` for the security motivation and intended scope; the existing `proxy-hosting` specification defines the routes and their other forwarding behavior.

## Goals / Non-Goals

**Goals:**

- Remove raw ASCII control bytes (`0x00`–`0x1F` and `0x7F`) from query strings before either proxy handler constructs its upstream URL.
- Preserve the order and value of every remaining query-string byte, including ordinary delimiters, non-ASCII bytes represented through `latin-1`, and percent-encoded text.
- Apply one consistent policy to both the UI and API proxy paths without changing their existing routing, authentication, wake-up, cookie, body, or response behavior.
- Make the policy directly unit-testable at the query-string boundary.

**Non-Goals:**

- Do not decode or normalize percent-encoded query values.
- Do not reject requests because a raw control byte is present; the selected compatibility behavior is silent removal.
- Do not change crew-id validation, upstream host selection, proxy authentication, session-cookie injection, request bodies, response streaming, or documentation outside the change's stated files.

## Decisions

### 1. Sanitize raw query bytes at the shared proxy URL boundary

Use a small shared helper that accepts the raw query-string bytes, decodes them with `latin-1`, and removes exactly the ASCII control range `0x00`–`0x1F` plus `0x7F`. Call it immediately before the UI and API handlers append the query to their upstream paths.

This keeps the security rule in one place and ensures both handlers receive identical treatment. Sanitizing after URL construction would leave the unsafe value in an intermediate URL, while duplicating the expression in each handler could allow the policies to diverge.

### 2. Strip rather than reject malformed raw controls

Strip control bytes silently instead of returning `400`. The proxy's normal clients should send valid query strings, but stripping is backward-compatible for malformed inputs and matches the proposal's preferred behavior. Rejecting would make the security fix an API behavior change for callers that can otherwise proceed safely after removal.

The alternative of stripping only CR and LF is narrower, but the full ASCII control range avoids leaving other request-line or parser controls in the upstream URL and is the explicitly selected policy.

### 3. Preserve percent-encoded data as query text

Operate on the raw query-string representation rather than parsing and re-encoding key/value pairs. A sequence such as `%0A` is printable query text and remains unchanged; it is not decoded into a control byte by this boundary sanitizer. `latin-1` provides a one-to-one mapping for non-control bytes so sanitization does not silently reinterpret the rest of the request.

### 4. Cover both proxy families and the preservation contract

Tests should exercise the helper or both handler call paths with raw CR, LF, and NUL bytes, and should assert that a normal query and percent-encoded values pass through unchanged. The implementation remains limited to the transport proxy module and its focused unit coverage.

## Risks / Trade-offs

- **[Risk]** Stripping bytes changes a malformed query rather than notifying the caller. → **Mitigation:** This is intentional and documented by the modified proxy requirements; valid and percent-encoded queries remain unchanged.
- **[Risk]** A future proxy path could bypass the shared helper. → **Mitigation:** Keep the helper shared and require both existing UI and API construction sites to call it; retain tests for both route families.
- **[Risk]** Raw control bytes may already be rejected by an HTTP server before reaching the application. → **Mitigation:** The boundary remains defensive for ASGI/test inputs and for any server configuration that accepts them; no reliance on upstream parser behavior is required.
- **[Risk]** `latin-1` is easy to misunderstand as a normalization step. → **Mitigation:** Document the one-to-one preservation contract in the helper and test non-control/percent-encoded values explicitly.

## Migration Plan

No configuration, data, or route migration is required. Ship the transport change with the normal image/application rollout, then run the focused proxy tests and the existing suite. If rollback is required, revert the single change commit; the existing proxy routes and all non-control query behavior remain compatible.
