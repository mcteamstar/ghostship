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

## 3. C-1 — Restore meaningful deleted test modules

- [x] 3.1 Create `tests/unit/test_streaming_transfer.py` covering
  `_ResponseChunkReader` and `_TarMemberStream` in `transport/files.py`:
  normal reads, cross-chunk boundaries, early EOF, and member-not-found error.
  Verify: `pytest tests/unit/test_streaming_transfer.py` passes.

  Dropped from scope (not genuine gaps):
  - `test_ws_proxy.py` — `_handle_crew_ui_ws_proxy` requires full async
    Starlette + websockets mock harness; belongs in integration tests
  - `test_podman_exec_stdin.py` — `container_exec_stdin` now covered by
    `TestInjectPolicyStdinDelivery` in `test_lifecycle.py` (task 2.3)
  - `test_tls.py` — `_ssl_context_factory` is a 6-line closure only reachable
    via server startup with real cert files; trivial and integration-only
  - `test_trn237_csp_nonce.py` — `generate_csp_nonce()` / `_csp_with_nonce()`
    are one-liner stdlib calls; no meaningful unit test gap
  - `test_trn221_no_hardcoded_sel_path.py` — no hardcoded SEL paths exist in
    codebase; guardrail would pass vacuously

## 4. Integration check

- [x] 4.1 Run `pytest tests/unit/` and confirm exit 0.
