## 1. Reconcile the httpx stub identity via a single shared stub module

- [ ] 1.1 Create `tests/unit/_stubs.py` containing the authoritative stub definitions currently inline in `test_file_transfer._install_import_stubs()`: the `httpx` module (with `Client`, `AsyncClient`, `HTTPTransport`, `Response`, `put`, `delete`) and, as **module-level classes** (not re-created per call), `HTTPStatusError`, `ConnectError`, `ConnectTimeout`; plus the `mcp`/`starlette`/`uvicorn` stubs.
- [ ] 1.2 In `tests/unit/_stubs.py`, implement `install_import_stubs()` to be **idempotent**: tag the installed httpx stub with a marker attribute (e.g. `_kirocrew_shared_stub = True`); if `sys.modules["httpx"]` already carries that marker, return without rebuilding — this guarantees every caller resolves the same object and the same `ConnectError`/`ConnectTimeout`/`HTTPStatusError` classes.
- [ ] 1.3 In `tests/unit/test_file_transfer.py`, replace the inline class/module definitions in `_install_import_stubs()` with a call to `tests.unit._stubs.install_import_stubs()` (keep the existing try/except that decides whether stubs are needed at all). Preserve the public `server = importlib.import_module("transport.server")` result and the `_install_import_stubs` name that `test_openapi` imports.
- [ ] 1.4 In `tests/unit/test_recovery.py`, remove `_ensure_httpx_exceptions()` (or reduce it to a call to `tests.unit._stubs.install_import_stubs()`) so it can no longer synthesize a divergent `ConnectError`/`ConnectTimeout`/`HTTPStatusError`. Confirm the tests still resolve `httpx.ConnectError` from `sys.modules` and that it is now `_stubs.ConnectError`.
- [ ] 1.5 Verify attribute-surface parity: `patch.object(server.httpx, "put", ...)` and any `patch.object(server.httpx, ...)`/`AsyncClient`/`Response` usages in `test_file_transfer`, `test_network`, `test_server` still work against the shared stub.
- [ ] 1.6 Do **NOT** add any `tearDownModule` / `setUpModule` that removes stub keys from `sys.modules`. The sequential runner requires the stubs to persist for `test_recovery`/`test_network`/`test_server`. Confirm no such hook was introduced.

## 2. Verify identity is reconciled and the suite is green

- [ ] 2.1 Add or confirm a targeted assertion that `transport.lifecycle`'s bound exception classes are identical to the ones tests raise, e.g. in a recovery test: `assert lifecycle.httpx.ConnectError is httpx.ConnectError` (documents the invariant and guards against regressions).
- [ ] 2.2 Run `python3 -m unittest tests.unit.test_file_transfer` in isolation — confirm it still passes.
- [ ] 2.3 Run `python3 -m unittest tests.unit.test_recovery` in isolation — confirm it passes.
- [ ] 2.4 Run `bash tests/run.sh --unit` (full sequential discovery) — confirm **zero** errors in `test_recovery`, `test_network`, `test_server`, and every other unit file. This is the authoritative acceptance signal (baseline was 11 `test_recovery` errors).
