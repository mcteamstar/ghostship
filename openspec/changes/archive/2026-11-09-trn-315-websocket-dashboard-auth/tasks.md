# Tasks

## 1. Enforce WebSocket authorization

- [x] 1.1 Share dashboard session validation with the WebSocket path and enforce it before crew lookup and upstream connection on keyed installations; verify missing, invalid, expired, revoked, malformed and duplicate cookies are rejected and a valid session passes.
- [x] 1.2 Enforce the portal transport secret for WebSocket scopes where configured; verify missing, incorrect and forged headers cannot reach the crew, and valid portal traffic works.
- [x] 1.3 Implement external dashboard origin validation for keyed installations using trusted configuration and portal metadata; verify matching HTTP/HTTPS origins, mismatches, malformed and duplicate headers, spoofed forwarding headers, supported proxy setups, and authenticated clients with no Origin.
- [x] 1.4 Preserve no-key operation and document the keyed, no-key and non-browser behavior; verify existing dashboard, login, logout and proxy unit tests and new open-mode cases.
- [x] 1.5 Preserve Origin validation when TLS is terminated before Caddy by deriving the external scheme from trusted portal configuration; cover managed TLS, plain HTTP, and upstream TLS termination without trusting client forwarding headers.

## 2. Verify the actual proxy path

- [x] 2.1 Add integration coverage through Caddy and the transport demonstrating that an ordinary unauthenticated HTTP request and cookie-free WebSocket upgrade are denied when keyed, and that an authenticated same-origin WebSocket exchanges frames with a disposable gateway.
- [x] 2.2 Verify the no-key dashboard handshake and frame relay and confirm bad credentials never cause crew startup or an upstream connection; run affected tests and record results.
- [x] 2.3 With explicit deployment authorization, install on a dev instance and reproduce the original 401/101 check as 401/denied, then verify authenticated live dashboard updates; record deployment and rollback evidence.

## Verification

- Full repository unit suite via `bash scripts/run.sh --unit`: 1,518 passed, 1 skipped. This includes dashboard, auth, Caddy, server, and WebSocket integration coverage.
- The crew's initial focused run passed 6 tests and skipped the real-Caddy case because Caddy was unavailable in that environment.
- The real-Caddy process test ran locally after isolating it from unit-test network stubs and correcting its Caddy invocation and client handling. Focused dashboard, Caddy, auth and server coverage: 218 passed.
- The merged build was installed on Corsair with a temporary API key: unauthenticated HTTP, missing/invalid-session WebSockets and an untrusted Origin were denied; valid same-origin and no-Origin sessions connected and exchanged ping/pong frames. The first valid handshake timed out at 10 seconds while a stopped crew was waking; a retry after wake succeeded. In an authenticated browser the dashboard connected, showed the task running and displayed a live Codex response. Corsair was restored to its normal no-key configuration and health passed; rollback would reinstall the previous branch build.
