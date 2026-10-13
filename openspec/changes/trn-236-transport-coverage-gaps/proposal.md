# Proposal

**Plane ticket:** TRN-236

## Why

Three substantial production paths in the transport have 0% test coverage as found in the 0.7.0 independent review (indy-070). The WebSocket proxy (`_handle_crew_ui_ws_proxy`) is 128 lines with no tests; the Claude login lifecycle has no tests while the equivalent Codex path is fully tested; and `container_exec_stdin` — the raw Unix socket hijack used by Claude login — is entirely uncovered. These are high-risk paths: the WS proxy is the primary crew dashboard interaction path, and the Claude login is the auth entry point for Claude-backend crews.

## What Changes

- **TC-1 — WS proxy tests**: Add tests for `_handle_crew_ui_ws_proxy` covering: upstream connection failure before client accept; normal bidirectional relay (mock WebSocket pairs); cookie near-expiry refresh mid-session; missing `websockets` dependency fallback. Use `unittest.mock` to fake the upstream WS connection.
- **TC-3 — Claude login lifecycle tests**: Add tests mirroring `test_trn212` (Codex login) for the Claude OAuth login path: `_start_claude_login_container`, `_nuke_claude_login_container`, `_initiate_claude_login` (binary probe loop, PTY exec, URL extraction). Mock `container_exec_stdin` for the PTY path.
- **TC-4 — `container_exec_stdin` unit tests**: Add `tests/unit/test_podman_exec_stdin.py` using `socketpair()` to simulate the Unix socket hijack: HTTP 101 upgrade sequence, bidirectional relay loop, exit-code extraction. Also add error-path tests for `container_networks`, `secret_create/delete`, `network_disconnect/rm`, `volume_create/remove`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `transport-test-coverage`: add requirements for WS proxy test coverage, Claude login lifecycle test coverage, and `container_exec_stdin` unit test coverage.

## Impact

- `tests/unit/test_ws_proxy.py` (new) — WS proxy coverage
- `tests/unit/test_claude_login.py` (new) — Claude login lifecycle
- `tests/unit/test_podman_exec_stdin.py` (new) — raw socket exec + Podman error paths
- No production code changes
