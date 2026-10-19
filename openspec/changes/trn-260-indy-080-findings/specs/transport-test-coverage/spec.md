# Spec delta — transport-test-coverage

## Changed requirements

### WebSocket proxy has test coverage

The test suite SHALL include `tests/unit/test_ws_proxy.py` covering
`_handle_crew_ui_ws_proxy`: upstream connection failure before client accept,
successful bidirectional relay, and abnormal close from either side.

### container_exec_stdin has test coverage

The test suite SHALL include `tests/unit/test_podman_exec_stdin.py` covering
`container_exec_stdin` using `socketpair()` to simulate the Unix socket
connection: normal write+read, write-end close triggers EOF on the reader, and
error propagation when the socket is unavailable.

### Streaming transfer classes have test coverage

The test suite SHALL include `tests/unit/test_streaming_transfer.py` covering
`_ResponseChunkReader` and `_TarMemberStream` in `transport/files.py`: normal
reads, cross-chunk boundaries, and early EOF.

### TLS context factory has test coverage

The test suite SHALL include `tests/unit/test_tls.py` covering
`_ssl_context_factory`: certfile+keyfile present → returns an `ssl.SSLContext`,
missing file → raises, and the no-TLS path returns `None`.

### CSP nonce injection has test coverage (TRN-237)

The test suite SHALL include `tests/unit/test_trn237_csp_nonce.py` covering the
Content-Security-Policy nonce middleware: nonce is injected into HTML responses,
non-HTML responses are unchanged, and the nonce value changes per request.

### No hardcoded SEL path static guardrail (TRN-221)

The test suite SHALL include `tests/unit/test_trn221_no_hardcoded_sel_path.py`
containing a static-assertion test that scans all Python files under
`transport/` and fails if any file contains a hardcoded pre-0.9.0 SEL path.
