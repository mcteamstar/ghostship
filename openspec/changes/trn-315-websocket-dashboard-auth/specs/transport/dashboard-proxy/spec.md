# Spec Delta

## MODIFIED Requirements

### Requirement: Per-crew dashboard routing when Portal enabled

`ga-portal` (Caddy) SHALL route each crew's dashboard port traffic to the transport's cookie-injecting proxy endpoint (`/crews/{crew_id}/ui/`) rather than directly to the crew gateway (`gs-{crew_id}:5476`). The transport proxy endpoint SHALL inject the crew's `mc_token_5476` session cookie on every forwarded request and SHALL handle both HTTP and WebSocket connections.

The crew gateway (`gs-{crew_id}:5476`) SHALL be reached exclusively from the transport. This satisfies the KiroCrew gateway's IP-binding constraint — the cookie is bound to the IP that performed the token exchange, which is `ga-transport`'s IP on `ga-net`.

#### Scenario: Dashboard request via Portal is authenticated

- **WHEN** a browser requests a crew dashboard port (e.g. `http://host:64058/`)
- **THEN** `ga-portal` proxies to `ga-transport:{PORT}/crews/{crew_id}/ui/`
- **THEN** the transport injects `Cookie: mc_token_5476=<crew_token>` on the forwarded request to `gs-{crew_id}:5476`
- **THEN** the KiroCrew SPA loads authenticated without a "Session expired" prompt

#### Scenario: WebSocket connections are proxied correctly

- **WHEN** the KiroCrew SPA opens a WebSocket connection through the dashboard port
- **THEN** the transport validates the client dashboard session and browser origin when dashboard authentication is enabled before opening the upstream connection
- **THEN** the transport proxy endpoint upgrades the connection and bidirectionally relays frames between the browser and `gs-{crew_id}:5476`
- **THEN** the upstream WebSocket handshake carries `Cookie: mc_token_5476=<crew_token>` and `Origin: http://localhost:{CREW_GATEWAY_PORT}` — the loopback origin is always in the gateway's `allowed_origins` set regardless of config
- **THEN** the gateway responds `101 Switching Protocols`

#### Scenario: Token expiry is handled transparently

- **WHEN** the stored `mc_token_5476` cookie's `session_exp` JWT claim is within 20% of `KC_GATEWAY_TOKEN_TTL` (default 24h) of expiring
- **THEN** the transport proxy endpoint re-mints the cookie before forwarding the request
- **THEN** the browser experiences no interruption
- **NOTE**: KiroCrew tokens are 2-part JWTs (`payload.signature`, not `header.payload.signature`). The `session_exp` claim (24h session lifetime) governs refresh; the `exp` claim is a short-lived one-time-URL TTL (~5 min) and SHALL NOT be used for the near-expiry check.

#### Scenario: Gateway 403 triggers cookie refresh

- **WHEN** the crew gateway returns 403 on a proxied request (e.g. after a container restart invalidates the stored cookie)
- **THEN** the transport re-mints the cookie and retries the request


## ADDED Requirements

### Requirement: Authenticate dashboard WebSocket clients

When dashboard API-key authentication is enabled, the transport SHALL validate the original client's unexpired and unrevoked dashboard session before connecting to the crew gateway. Browser-origin handshakes SHALL also require an origin matching the externally visible dashboard origin; untrusted forwarded headers SHALL NOT establish that origin. Reject malformed or conflicting origins and do not forward upstream on rejection. Non-browser clients without an Origin MAY connect with a valid session. When API-key authentication is disabled, the existing open access behavior SHALL remain available.

#### Scenario: Missing or invalid session
- **WHEN** a client on a keyed installation opens a dashboard WebSocket with no, invalid, expired, or revoked session
- **THEN** the handshake is denied and no upstream connection is made

#### Scenario: Valid same-origin browser session
- **WHEN** a client presents a valid session and the matching dashboard origin
- **THEN** the WebSocket connects and relays frames

#### Scenario: Cross-origin browser request
- **WHEN** a client presents a valid session with an untrusted, malformed, or conflicting Origin
- **THEN** the handshake is denied before the upstream connection

#### Scenario: Valid non-browser client
- **WHEN** a non-browser client presents a valid session without an Origin
- **THEN** it may connect through the dashboard proxy

#### Scenario: Open installation
- **WHEN** API-key authentication is disabled
- **THEN** a dashboard WebSocket may connect without a session as before
