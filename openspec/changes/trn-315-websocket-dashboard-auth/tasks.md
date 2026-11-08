# Tasks

## 1. Enforce WebSocket authorization

- [x] 1.1 Share dashboard session validation with the WebSocket path and enforce it before crew lookup and upstream connection on keyed installations; verify missing, invalid, expired, revoked, malformed and duplicate cookies are rejected and a valid session passes.
- [x] 1.2 Enforce the portal transport secret for WebSocket scopes where configured; verify missing, incorrect and forged headers cannot reach the crew, and valid portal traffic works.
- [x] 1.3 Implement external dashboard origin validation for keyed installations using trusted configuration and portal metadata; verify matching HTTP/HTTPS origins, mismatches, malformed and duplicate headers, spoofed forwarding headers, supported proxy setups, and authenticated clients with no Origin.
- [x] 1.4 Preserve no-key operation and document the keyed, no-key and non-browser behavior; verify existing dashboard, login, logout and proxy unit tests and new open-mode cases.

## 2. Verify the actual proxy path

- [x] 2.1 Add integration coverage through Caddy and the transport demonstrating that an ordinary unauthenticated HTTP request and cookie-free WebSocket upgrade are denied when keyed, and that an authenticated same-origin WebSocket exchanges frames with a disposable gateway.
- [x] 2.2 Verify the no-key dashboard handshake and frame relay and confirm bad credentials never cause crew startup or an upstream connection; run affected tests and record results.
- [ ] 2.3 With explicit deployment authorization, install on a dev instance and reproduce the original 401/101 check as 401/denied, then verify authenticated live dashboard updates; record deployment and rollback evidence.

## Verification

- Dashboard, login/logout, auth, Caddy, server, and WebSocket integration suites: 309 tests passed using the repository's unittest-compatible tests and dependency stubs. The Python environment does not include pytest.
- The WebSocket integration coverage inspects generated Caddy route configuration and exercises the transport ASGI path with a disposable gateway double. No live Caddy process or dev instance was used.
- Task 2.3 remains gated because explicit deployment authorization was not provided.
