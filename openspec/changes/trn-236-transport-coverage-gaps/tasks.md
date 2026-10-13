# Tasks

## 1. WS proxy tests

- [x] 1.1 Create `tests/unit/test_ws_proxy.py`. Mock the WebSocket connection using `unittest.mock.AsyncMock`. Add tests covering: upstream connection failure before client accept → handler returns non-2xx; normal bidirectional relay → client messages forwarded to upstream and vice versa; cookie near-expiry detected mid-session → refresh called and connection continues. Verify: `tests/run.sh --unit` passes.

## 2. Claude login lifecycle tests

- [x] 2.1 Create `tests/unit/test_claude_login.py` mirroring the structure of `tests/unit/test_trn172_codex_backend.py`. Mock `container_exec_stdin` for PTY interaction. Cover: `_start_claude_login_container` starts container and probes for binary; `_initiate_claude_login` extracts URL from PTY output; `_initiate_claude_login` times out when no URL appears and nukes container; `_nuke_claude_login_container` removes the container. Verify: `tests/run.sh --unit` passes.

## 3. container_exec_stdin unit tests

- [x] 3.1 Create `tests/unit/test_podman_exec_stdin.py`. Use `socket.socketpair()` to simulate the Unix socket connection. Cover: HTTP 101 upgrade handshake sequence; stdin content forwarded to socket; socket output forwarded to stdout; exit-code extraction from trailer. Verify: `tests/run.sh --unit` passes.
- [x] 3.2 Add error-path tests for Podman management methods: `secret_create` fails → exception raised; `secret_delete` on non-existent secret → handled gracefully; `network_disconnect` error → logged and raised; `volume_create` failure → exception raised; `volume_remove` on non-existent volume → handled. Verify: `tests/run.sh --unit` passes.

## 4. Integration check

- [x] 4.1 Run `tests/run.sh --unit` with all new tests together. Confirm no regressions.

## Workflow follow-up

- Archive the change after review.
