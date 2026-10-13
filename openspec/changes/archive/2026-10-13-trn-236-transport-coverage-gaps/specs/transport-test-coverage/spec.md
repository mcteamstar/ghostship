# Spec Delta

## ADDED Requirements

### Requirement: _handle_crew_ui_ws_proxy test coverage
The test suite SHALL exercise `_handle_crew_ui_ws_proxy` covering: upstream connection failure before client accept (returns 502); normal bidirectional relay (client→upstream and upstream→client message forwarding); cookie near-expiry refresh mid-session (refresh is called and connection continues); missing `websockets` dependency (returns 501 or logs appropriate error).

#### Scenario: WS proxy handles upstream failure before accept
- **WHEN** `_handle_crew_ui_ws_proxy` is called and the upstream WebSocket connection fails before the client connection is accepted
- **THEN** the handler returns a non-2xx HTTP response without crashing

#### Scenario: WS proxy relays messages bidirectionally
- **WHEN** `_handle_crew_ui_ws_proxy` establishes both connections successfully
- **THEN** messages sent from the client are forwarded to upstream, and messages from upstream are forwarded to the client

### Requirement: Claude login lifecycle test coverage
The test suite SHALL exercise the Claude OAuth login flow: `_start_claude_login_container` (container start, binary probe), `_initiate_claude_login` (PTY exec, URL extraction, timeout), and `_nuke_claude_login_container` (container cleanup). Tests SHALL mirror the structure of the existing Codex login tests (`test_trn172_codex_backend.py`). `container_exec_stdin` SHALL be mocked for PTY interaction.

#### Scenario: Claude login extracts URL from PTY output
- **WHEN** `_initiate_claude_login` runs and the PTY emits a login URL
- **THEN** the URL is extracted and returned as the login URL

#### Scenario: Claude login times out if no URL appears
- **WHEN** `_initiate_claude_login` runs and no URL appears within the timeout
- **THEN** the login container is nuked and a timeout error is returned

### Requirement: container_exec_stdin unit test coverage
The test suite SHALL include unit tests for `container_exec_stdin` using `socketpair()` to simulate the Unix socket connection, covering: HTTP 101 upgrade handshake; bidirectional relay (stdin→socket, socket→stdout); exit-code extraction from the trailer. Error-path tests SHALL cover `secret_create` / `secret_delete`, `network_disconnect` / `network_rm`, and `volume_create` / `volume_remove` Podman management methods.

#### Scenario: container_exec_stdin completes HTTP 101 upgrade
- **WHEN** `container_exec_stdin` is called with a mock socket that responds with HTTP 101
- **THEN** the upgrade handshake completes and the stdin content is forwarded to the socket

#### Scenario: container_exec_stdin extracts exit code from trailer
- **WHEN** the exec session ends and the socket sends a trailer with exit code
- **THEN** `container_exec_stdin` returns the correct exit code
