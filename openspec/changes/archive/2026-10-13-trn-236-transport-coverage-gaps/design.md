# Design

## Context

See `proposal.md` — Why. Three uncovered production paths in the transport are
targeted: the WebSocket reverse proxy, the Claude OAuth login lifecycle, and the
raw Unix-socket exec hijack. This is a **test-only** change: no production code
is modified, so the design is about how to exercise code that was written to
talk to live infrastructure (a Podman socket, a crew gateway, a PTY) without any
of that infrastructure present.

Relevant current state, confirmed from the code:

- `_handle_crew_ui_ws_proxy` (`transport/server.py:1183`) is an **ASGI
  WebSocket-scope** handler, not an HTTP handler. It opens the upstream with
  `websockets.connect(...)` as an async context manager and accepts the client
  connection *only after* the upstream handshake succeeds. On failure it does
  **not** return an HTTP status — it closes the client WS with a close code
  (`1011` internal / `1008` policy). It also early-returns a `websocket.close`
  with code `1011` when either `_StarletteWebSocket` or `websockets` is `None`
  (the dependency-free path). Cookie refresh happens inline via
  `_cookie_near_expiry` / `_refresh_cookie` before the upstream dial.
- `container_exec_stdin` (`transport/podman.py:517`) POSTs an exec spec, then
  opens a raw `AF_UNIX` socket, sends an HTTP `Upgrade: tcp` request, reads
  until the `\r\n\r\n` that terminates the `101 Switching Protocols` headers,
  writes `stdin_data`, half-closes with `SHUT_WR`, drains the response, demuxes
  it with `self._demux`, then inspects `/libpod/exec/{id}/json` for `ExitCode`.
- The Claude login lifecycle lives in `transport/lifecycle.py`:
  `_start_claude_login_container` (2395), `_nuke_claude_login_container` (2431),
  `_initiate_claude_login` (2919). The equivalent Codex path is already covered
  by `tests/unit/test_trn172_codex_backend.py` and `test_trn212_codex_login.py`,
  which the new tests mirror.
- Unit tests install import stubs **before** importing any `transport` module
  (`from tests.unit._stubs import install_import_stubs; install_import_stubs()`)
  and run under `tests/run.sh --unit`.

## Goals / Non-Goals

**Goals:**

- Exercise each path against its *real* observable contract (actual close
  codes, actual exit-code extraction, actual URL extraction), not an idealised
  one.
- Reuse the existing stub-first import discipline and the Codex login tests as
  the structural template, so the new tests fit the suite's conventions.
- Drive the raw-socket and PTY paths with in-process fakes (`socketpair`,
  `AsyncMock`, a mocked `container_exec_stdin`) so no Podman socket, crew
  gateway, or container is required.

**Non-Goals:**

- No production code changes — including no refactor to make a path "more
  testable". Where the real contract diverges from the proposal's prose
  (see Decisions), the **test asserts the real behaviour** and the divergence
  is noted, not "fixed".
- No end-to-end or integration coverage against a live Podman/crew gateway;
  these remain unit tests.
- No coverage of paths outside the three named targets and the enumerated
  Podman error-path methods.

## Decisions

### D1 — Assert the WS proxy's real close-code contract, not "502"

The proposal and spec delta describe upstream failure as "returns 502 / returns
a non-2xx HTTP response". The handler is a WebSocket-scope handler and has no
HTTP response to return; it closes the client WS with **code `1011`** (upstream
dial failure) or **`1008`** (unknown crew / policy), and emits a bare
`websocket.close` `1011` on the missing-dependency path.

**Decision:** tests assert the actual ASGI close frames. The "502" in the
spec is the *semantic* intent (an upstream failure surfaced to the client as a
server-side error); the test encodes it as the close code the code truly sends.
The spec's scenario wording ("non-2xx HTTP response without crashing") is
satisfied by "closes cleanly with a server-error close code".

**Alternative considered:** change the handler to translate failures into an
HTTP 502 before the WS upgrade. Rejected — this is a test-only change, and the
upgrade has usually already begun, so an HTTP status is not available to send.

### D2 — Fake both WS sides with `AsyncMock`, drive the upstream context manager

The upstream is entered as `async with websockets.connect(...) as upstream`.

**Decision:** patch `transport.server._websockets.connect` to return an object
whose `__aenter__` yields a configured `AsyncMock` upstream; patch
`_StarletteWebSocket` to a fake client whose `receive()` is scripted to emit a
text frame, then a binary frame, then `{"type": "websocket.disconnect"}`.
Relay assertions check that client frames reached `upstream.send` and that
frames yielded by `async for message in upstream` reached `ws.send_text` /
`ws.send_bytes`. The missing-dependency case is covered by setting
`_websockets` (or `_StarletteWebSocket`) to `None` and asserting the single
`websocket.close` 1011 send.

**Alternative considered:** a real loopback WebSocket server. Rejected — heavier,
flakier, and needs the `websockets` dependency the dependency-free scenario is
specifically meant to exercise *without*.

### D3 — Cookie-refresh assertion via patched helpers

**Decision:** patch `_cookie_near_expiry` to return `True` and assert
`_refresh_cookie` is called before the upstream dial, with the relay then
proceeding normally. This isolates the refresh branch from real cookie/TTL math,
which is out of scope here.

### D4 — `socketpair()` as the hijacked Podman socket

`container_exec_stdin` connects a fresh `AF_UNIX` socket to `self._sock_path`.

**Decision:** inject one end of `socket.socketpair()` as the client socket (by
patching the `socket.socket(...).connect` seam / the `_sock_path` dial so the
code under test receives our end), and drive the Podman side from the test on
the other end: write the `HTTP/1.1 101 Switching Protocols\r\n\r\n` header block,
then a `_demux`-framed stdout payload, then close to signal EOF. The exec spec
POST and the `/libpod/exec/{id}/json` inspect are stubbed on the HTTP client
(`self._c` / `self._req`) to return a fixed `Id` and `ExitCode`. Assertions:
the handshake is consumed up to `\r\n\r\n`; `stdin_data` arrives on the test end;
demuxed stdout is returned; the stubbed `ExitCode` is honoured (0 → return,
non-zero → `RuntimeError`).

**Alternative considered:** mock `socket` entirely with `Mock`/`AsyncMock`.
Rejected — a real `socketpair()` exercises the actual `sendall`/`recv`/`shutdown`
sequence and the real buffering boundary (headers arriving in the same chunk as
early output), which the handshake-parsing logic depends on; a pure mock would
not catch a regression there.

### D5 — Mock `container_exec_stdin` for the Claude PTY path

`_initiate_claude_login` calls `container_exec_stdin` to drive the login binary.

**Decision:** mirror `test_trn172_codex_backend.py` — mock
`container_exec_stdin` to return canned PTY output containing a login URL for
the happy path, and output with **no** URL for the timeout path, then assert
`_nuke_claude_login_container` is invoked and a timeout error surfaces.
`_start_claude_login_container`'s binary-probe loop is covered by stubbing the
probe exec to succeed/need-retry. This keeps the Claude tests structurally
identical to the already-reviewed Codex tests.

**Alternative considered:** a pseudo-terminal via `pty.openpty()`. Rejected —
the spec explicitly says mock `container_exec_stdin`, and a real PTY adds
platform-dependent flakiness without exercising additional login-handler logic.

### D6 — Podman error-path tests target observable behaviour per method

**Decision:** for `secret_create` / `volume_create` / `network_rm`, stub the
underlying HTTP call to a non-2xx response and assert the method raises (via its
`_check_response`). For the "handled gracefully on non-existent" cases
(`secret_delete`, `volume_remove`, `network_disconnect`), stub a 404/already-gone
response and assert the method returns without raising. Each assertion follows
the method's real error contract rather than a uniform rule.

## Risks / Trade-offs

- **[Spec/code wording mismatch on "502"]** → D1 resolves it by asserting the
  real close codes and treating "502/non-2xx" as semantic intent. The reviewer
  should expect close-code assertions, not an HTTP-status assertion, in
  `test_ws_proxy.py`.
- **[`socketpair` framing fragility — the 101 headers and early stdout can
  arrive in one chunk]** → the test writes the header block and payload as
  distinct `send` calls but also includes one case where they are coalesced into
  a single write, matching the leftover-handling the production code documents
  (`podman.py:380,439`).
- **[Async fakes can hang if a relay task never terminates]** → every scripted
  client `receive()` ends with a `websocket.disconnect`, and the upstream
  `AsyncMock` async-iterator is finite, so `asyncio.wait` on the relay tasks
  always resolves; tests additionally wrap awaits in a short timeout.
- **[Over-mocking hides real breakage]** → mitigated by using a real
  `socketpair()` (D4) for the one path whose value is the byte-level socket
  dance; the PTY and WS paths are legitimately pure-logic once their I/O seam is
  faked.
- **[Stub-order regressions]** → all three test files call
  `install_import_stubs()` before importing any `transport` module, matching the
  existing suite; a missed stub surfaces immediately as an ImportError under
  `tests/run.sh --unit`.

## Migration Plan

Not applicable — test-only change, no runtime, data, or deployment impact.
Rollback is deletion of the three new test files; no production surface is
touched. Verification is `tests/run.sh --unit` passing with the new tests
added (tasks 1–4).

## Open Questions

None. The one ambiguity (the "502" wording) is resolved at design time in D1
rather than deferred, because leaving it open would change what the tests
assert.
