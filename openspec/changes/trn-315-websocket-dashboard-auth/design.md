# Design

## Context

Caddy deliberately sends upgrades directly to the transport, while ordinary dashboard HTTP requests use `/dashboard/auth`. The WebSocket handler opens the crew connection with Ghostship's gateway cookie and replaces the upstream origin. Existing `transport/caddy-proxy` requirements already call for a transport-side session check; the implementation omitted it.

## Goals / Non-Goals

**Goals:** Enforce the original client's session and protect browser handshakes against cross-site use; retain authenticated dashboard functionality and no-key installations.

**Non-Goals:** Change KiroCrew authentication, expose gateway credentials, or redesign dashboard login.

## Decisions

1. Enforce at the transport WebSocket dispatch boundary before crew lookup, cookie refresh, or upstream connection. Reuse the dashboard gate's existing `SessionStore` and key-enabled condition, sharing validation with HTTP instead of duplicating a token store. Fail closed for missing, invalid, expired, revoked, malformed, or duplicate session cookies. A rejected client must not cause crew startup or gateway access. Caddy-only forward auth was considered, but the existing upgrade handling exists because its subrequest interfered with upgrades; transport enforcement also protects direct internal routes.
2. For keyed deployments, validate an incoming browser Origin against the actual external dashboard scheme, host and port. Treat forwarded host/proto as trusted only from the authenticated portal boundary, and fail closed on ambiguous, malformed, duplicate or conflicting headers; do not derive trust from an arbitrary client-supplied Host or forwarded header. Derive expected origins from configured external host/TLS mode and the registered crew dashboard port. Test plain HTTP and configured TLS, including reverse-proxy deployment forms supported by configuration. Permit absent Origin for authenticated non-browser clients. No-key mode retains its current open behavior.
3. Reject before acceptance using the ASGI denial response supported by the deployed server; if unavailable use a pre-accept close that does not upgrade. Never expose session or gateway cookies in logs or errors. Existing established sockets need not be terminated on subsequent logout; expiry and revocation apply to new handshakes.

## Risks / Trade-offs

- Incorrect external origin derivation can break valid deployments → cover supported host, port, TLS and proxy configurations and document the rule.
- Direct access to transport or forged portal headers can bypass an origin boundary → verify transport-secret enforcement for WebSocket scopes independently and reject direct requests in keyed deployments when the secret is configured.
- A 101 alone proves a handshake, not event access → use non-sensitive disposable test data when verifying frame relay.

## Migration Plan

Deploy updated transport and recreate/re-register dashboard routes if required; existing sessions remain valid. Check a keyed dashboard and an open installation. Roll back by redeploying the previous release if necessary, recognising that rollback restores the authentication bypass.
