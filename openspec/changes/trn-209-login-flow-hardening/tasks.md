## 1. PTY byte-loss fix (transport/podman.py)

- [ ] 1.1 Change `container_exec_pty_stdin` return type to `tuple[str, socket.socket, bytes]`; after the `\r\n\r\n` header loop, slice `response_buf` at the delimiter offset and return the remainder as the third element.
- [ ] 1.2 Add `sock.settimeout(PTY_SOCKET_TIMEOUT_SECS)` (constant: 120 s) before the header-read loop in `container_exec_pty_stdin`; document that callers calling `setblocking(False)` override this for subsequent reads.
- [ ] 1.3 Update type annotation and docstring on `container_exec_pty_stdin` to reflect the new three-tuple return.

## 2. PTY helper — seed accumulator from leftover bytes (transport/lifecycle.py)

- [ ] 2.1 Add `initial_bytes: bytes = b""` parameter to `_run_pty_login_flow`; pre-populate `collected` with it before the select-loop.
- [ ] 2.2 Update the kiro call-site (`_initiate_login`): unpack `(exec_id, pty_sock, leftover)` from `container_exec_pty_stdin`; pass `initial_bytes=leftover` to `_run_pty_login_flow`.
- [ ] 2.3 Update the Claude call-site (`_initiate_claude_login`): same — unpack three values, pass leftover bytes.
- [ ] 2.4 Update the Codex call-site (`_initiate_codex_login`): same — unpack three values, pass leftover bytes.

## 3. Login expiry sweep — kiro and Codex (transport/lifecycle.py)

- [ ] 3.1 Define `KIRO_LOGIN_TTL_SECS = 900.0` and `CODEX_LOGIN_TTL_SECS = 900.0` module-level constants alongside the existing `CLAUDE_LOGIN_APPROVAL_DEADLINE_SECS`.
- [ ] 3.2 Write `_kiro_login_expired(pending: dict) -> bool`: returns `True` when `started_at` is set and `time.time() - started_at > KIRO_LOGIN_TTL_SECS`.
- [ ] 3.3 Write `_codex_login_expired(pending: dict) -> bool`: same pattern using `CODEX_LOGIN_TTL_SECS`.
- [ ] 3.4 Write `_sweep_expired_logins(podman: PodmanClient) -> None`: under each backend's lock, snapshot the pending dict; if the dict is non-None and the matching `*_expired` predicate returns True, nuke the container (best-effort) then clear the pending dict; log each expiry at WARNING level.
- [ ] 3.5 Wire `_sweep_expired_logins` into the existing startup/maintenance sweep path (the function near line 1581 that already sweeps orphaned login containers); pass the `podman` client it already holds.

## 4. Login expiry sweep — Claude (transport/lifecycle.py)

- [ ] 4.1 Verify that `_claude_login_code_expired` is called inside `_sweep_expired_logins` (D3) using the existing `CLAUDE_LOGIN_APPROVAL_DEADLINE_SECS` / `CLAUDE_LOGIN_CODE_DEADLINE_SECS` constants — so Claude expiry fires without a poll, not only inside `server.py` handlers.

## 5. Codex device-code regex (transport/lifecycle.py)

- [ ] 5.1 Replace `codex_code_pattern` in `_initiate_codex_login` with a regex that restricts the prose branch to uppercase-or-digit tokens of 4–8 chars with a word boundary; keep the `user_code=` URL-param branch unchanged.
- [ ] 5.2 Update the `code_pattern` capture-group extraction in `_run_pty_login_flow` (or in `_initiate_codex_login` post-call) so the two-branch pattern's groups are handled correctly (e.g., `group(1) or group(2)`).
- [ ] 5.3 Add a unit test for the new pattern: assert "will" is not captured from "The code will expire in 15 minutes"; assert a real-looking code (`ABCD1234`) is captured from "Code: ABCD1234".

## 6. Tests — PTY byte loss

- [ ] 6.1 Write a socketpair test for `container_exec_pty_stdin`: fake the server side sending `HTTP/1.1 101 ...\r\n\r\n<PTY bytes>` as one chunk; assert the returned `leftover` bytes equal `<PTY bytes>`.
- [ ] 6.2 Write a test for `_run_pty_login_flow` with `initial_bytes` set to a synthetic URL string; assert the URL is extracted without any `select` loop receiving further data.

## 7. Tests — expiry sweep

- [ ] 7.1 Unit-test `_kiro_login_expired` and `_codex_login_expired` with `started_at` values before and after their TTL.
- [ ] 7.2 Write an integration-style test for `_sweep_expired_logins`: mock `podman`, pre-populate all three pending dicts with expired state, call the sweep, assert all three are cleared and the mock nuke functions were called.
- [ ] 7.3 Write a test for the Claude sweep path: pre-populate `_claude_login_pending` in `awaiting_code` state with an old `started_at`; call `_sweep_expired_logins`; assert the dict is cleared.

## 8. Regression — Codex poll without patch

- [ ] 8.1 Verify existing Codex poll tests (`test_codex_login_poll` or equivalent) still pass after the regex change; if they rely on patching `_run_pty_login_flow`, ensure at least one test runs the real regex path.
