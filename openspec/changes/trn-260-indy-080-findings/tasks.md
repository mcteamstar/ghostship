# Tasks

## 1. Quick fixes (L-1, M-4)

- [x] 1.1 In `transport/config.py`, change the `ga_dashboard_port_range_size`
  dataclass default from `1024` to `64`. Verify: `grep ga_dashboard_port_range_size transport/config.py`
  shows `64`; unit tests pass.

- [x] 1.2 In `transport/files.py`, replace all 3 calls to `hmac.new(...)` with
  `hmac.HMAC(...)` (identical signature). Verify: `grep -n 'hmac\.new' transport/files.py`
  returns nothing; unit tests pass.

## 2. H-1 — stdin delivery for inject_policy.py

- [x] 2.1 Update `transport/container_scripts/inject_policy.py` to read the HMAC
  signing key from `sys.stdin.read().strip()` instead of `sys.argv[1]`. Remove
  the `--key` / positional argv handling. Verify: running the script with key
  piped via stdin works; `sys.argv` no longer contains the key value.

- [x] 2.2 Update the caller in `transport/lifecycle.py` (the
  `container_exec_stdin` call for `inject_policy.py`) to pass the key via the
  `input=` kwarg instead of as an argv element. Verify: no `--key` or raw key
  string in the argv list passed to `container_exec_stdin` for inject_policy.

- [x] 2.3 Add a unit test in `tests/unit/test_lifecycle.py` (or a new dedicated
  file) asserting that the argv list for `inject_policy.py` does not contain
  the HMAC key, and that the key is delivered via the `input` kwarg. Verify:
  test passes and fails against the pre-fix code.

## 3. C-1 — Restore deleted test modules

- [ ] 3.1 Create `tests/unit/test_ws_proxy.py` covering `_handle_crew_ui_ws_proxy`:
  upstream failure before accept, successful relay, abnormal close. Verify:
  `pytest tests/unit/test_ws_proxy.py` passes.

- [ ] 3.2 Create `tests/unit/test_podman_exec_stdin.py` covering
  `container_exec_stdin` with `socketpair()`: normal write+read, EOF on close,
  error propagation. Verify: `pytest tests/unit/test_podman_exec_stdin.py` passes.

- [ ] 3.3 Create `tests/unit/test_streaming_transfer.py` covering
  `_ResponseChunkReader` and `_TarMemberStream`: normal reads, chunk boundaries,
  early EOF. Verify: `pytest tests/unit/test_streaming_transfer.py` passes.

- [ ] 3.4 Create `tests/unit/test_tls.py` covering `_ssl_context_factory`:
  cert+key present → `SSLContext`, missing file → raises, no-TLS → `None`.
  Verify: `pytest tests/unit/test_tls.py` passes.

- [ ] 3.5 Create `tests/unit/test_trn237_csp_nonce.py` covering CSP nonce
  middleware: nonce injected into HTML, non-HTML unchanged, nonce rotates per
  request. Verify: `pytest tests/unit/test_trn237_csp_nonce.py` passes.

- [ ] 3.6 Create `tests/unit/test_trn221_no_hardcoded_sel_path.py` as a static
  guardrail scanning `transport/` Python files for hardcoded pre-0.9.0 SEL
  paths. Verify: `pytest tests/unit/test_trn221_no_hardcoded_sel_path.py` passes.

## 4. Integration check

- [ ] 4.1 Run `pytest tests/unit/` and confirm exit 0.
