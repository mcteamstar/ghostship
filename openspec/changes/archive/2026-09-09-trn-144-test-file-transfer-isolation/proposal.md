## Why

Under full-suite discovery (`bash tests/run.sh --unit`), all 11 `test_recovery` tests error even though `test_file_transfer` and `test_recovery` each pass in isolation. The failure is an **httpx stub-class identity mismatch**, not stub *leakage* under a parallel runner:

- The unit runner is **sequential** (`python3 -m unittest discover`, `tests/run.sh` line 110) — not `unittest-parallel`. There is no parallel scheduling to isolate against.
- `transport.lifecycle` (line 32) does `import httpx` and binds `except (httpx.ConnectError, httpx.ConnectTimeout, ...)` (line 495) to the `ConnectError` class of whichever httpx stub object is in `sys.modules` at its import time.
- `test_recovery.py` raises `httpx.ConnectError(...)` (lines 210, 235, 281, 353) resolved from *its own* `import httpx`.
- When full-discovery import ordering causes `test_recovery`'s `_ensure_httpx_exceptions()` to synthesize a **fresh** `ConnectError` class (because it inspects a stub that does not yet carry the attribute at that moment), the class the test raises is a different object than the class `lifecycle`'s `except` clause references. The `except httpx.ConnectError` therefore never matches, the exception escapes `_crew_api_with_recovery`, and the recovery test errors.

The previously-prescribed fix (snapshot `sys.modules` before stubs, restore in `tearDownModule`) is **rejected**: it does not address identity, and it actively regresses the suite. `test_recovery`, `test_network`, and `test_server` deliberately `from tests.unit.test_file_transfer import server` / `_install_import_stubs`, reusing the stub httpx/server installed by `test_file_transfer`. A `tearDownModule` that removes those stubs mid-suite (the runner is sequential, so it fires *before* those downstream modules run) desynchronizes them and adds ~10 new errors on top of the original 11.

## What Changes

- Introduce a **single shared stub module** (e.g. `tests/unit/_stubs.py`) that is the one authoritative source of the fake `httpx`/`mcp`/`starlette`/`uvicorn` modules and their exception classes.
- `test_file_transfer._install_import_stubs()` installs the stubs from this shared module (behaviour otherwise unchanged); every test file (`test_recovery`, `test_network`, `test_server`, `test_openapi`) and `transport.lifecycle` resolve the **same** httpx object, so `httpx.ConnectError` / `httpx.ConnectTimeout` / `httpx.HTTPStatusError` are one class each across the whole suite.
- Remove `test_recovery._ensure_httpx_exceptions()`'s ability to synthesize divergent exception classes — the shared stub always carries them, so the `hasattr`-guarded fallback either becomes unnecessary or is made idempotent against the shared classes.
- **No `tearDownModule` `sys.modules` restore.** Stubs remain installed for the duration of the sequential suite, as the downstream test files require.
- No changes to production code behaviour (`transport/*` unchanged except, if needed, importing the stub is confined to test scope).

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

_(none — `skip_specs: true` — pure test-infrastructure change, no spec-level behaviour)_

## Impact

- `tests/unit/_stubs.py` — new module: the single source of stub httpx/mcp/starlette/uvicorn and their exception classes
- `tests/unit/test_file_transfer.py` — `_install_import_stubs()` installs from the shared module instead of defining classes inline
- `tests/unit/test_recovery.py` — drop or neutralize `_ensure_httpx_exceptions()` so it can no longer create a divergent `ConnectError`
- `bash tests/run.sh --unit` passes cleanly: zero errors in `test_recovery`, `test_network`, `test_server`, and `test_file_transfer` in isolation still passes
