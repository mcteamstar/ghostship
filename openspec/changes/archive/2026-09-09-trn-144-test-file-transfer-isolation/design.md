## Context

`tests/unit/test_file_transfer.py` uses a try/except at module scope so the suite runs in a dependency-free checkout:

```python
try:
    server = importlib.import_module("transport.server")
except ModuleNotFoundError:
    _install_import_stubs()          # writes fake httpx/mcp/starlette/uvicorn into sys.modules
    server = importlib.import_module("transport.server")
```

`_install_import_stubs()` defines `class ConnectError(Exception)`, `class ConnectTimeout(Exception)`, `class HTTPStatusError(Exception)` **inline** and assigns them onto a fresh `httpx` stub module, then `sys.modules["httpx"] = httpx`.

Downstream test files depend on that stub rather than re-installing their own:

- `test_recovery.py` line 39: `from tests.unit.test_file_transfer import server` (triggers the stub install as a side effect), then `import transport.lifecycle as lifecycle`, then its own `import httpx`. It also defines `_ensure_httpx_exceptions()` which, guarded by `hasattr(_httpx, "ConnectError")`, will **synthesize a brand-new `ConnectError` class** if the attribute is absent at that instant.
- `test_network.py` / `test_server.py` / `test_openapi.py` similarly reuse `test_file_transfer`'s stubs (`test_openapi` calls `_install_import_stubs()` directly).

`transport/lifecycle.py` line 32 does `import httpx` and at line 495 binds:

```python
except (httpx.ConnectError, httpx.ConnectTimeout, ConnectionError, OSError):
    return _phase2_dead_gateway(...)
```

This `except` clause captures class *objects*, resolved from `sys.modules["httpx"]` at lifecycle import time.

## Problem (corrected root cause)

The failure is a **stub-class identity mismatch**, exposed by full-discovery import order — not stub leakage under a parallel runner.

1. **The runner is sequential.** `tests/run.sh` line 110 runs `python3 -m unittest discover -s tests/unit -p "test_*.py" -t .`. No `unittest-parallel`. The original proposal's premise (parallel scheduling picks up leaked stubs) is false.
2. **Downstream files intentionally reuse the stub.** `test_recovery`, `test_network`, `test_server`, `test_openapi` import `test_file_transfer` precisely to reuse its installed stub httpx/server. They must see the stub for the whole run.
3. **The identity split.** `lifecycle`'s `except httpx.ConnectError` references the `ConnectError` object present on the httpx stub at lifecycle-import time. `test_recovery` raises `httpx.ConnectError(...)` resolved from its own `import httpx`. When import ordering under full discovery causes `_ensure_httpx_exceptions()` to run against a stub whose `ConnectError` attribute is not yet present (or against a different stub object), it creates a *second* `ConnectError` class. The test then raises class **B** while `lifecycle` catches only class **A** → the exception is never caught → all 11 `test_recovery` tests error. In isolation the ordering lines up and the classes coincide, so the tests pass.

## Why `tearDownModule` sys.modules snapshot/restore is REJECTED

The prior design proposed snapshotting `sys.modules` before the stubs and restoring in `tearDownModule`. This is wrong on two independent counts, both confirmed empirically by Ghost (baseline: 11 errors; with the change: ~21 errors):

- **It does not touch identity.** The 11 errors come from two `ConnectError` classes existing at once, not from a stray key in `sys.modules`. Restoring keys after the module's tests finish changes nothing about which class object `lifecycle` already bound.
- **It regresses the sequential suite.** Because the runner is sequential, `tearDownModule` fires when `test_file_transfer`'s tests finish — *before* `test_recovery` / `test_network` / `test_server` run. Those modules deliberately depend on the stub httpx/server still being in `sys.modules`. Ripping it out mid-suite desynchronizes them and adds ~10 new errors on top of the original 11.

`tearDownModule` restore is therefore off the table for this change.

## Goals / Non-Goals

**Goals:**
- `bash tests/run.sh --unit` passes cleanly: zero errors across `test_recovery`, `test_network`, `test_server`.
- `lifecycle` and every test file resolve the **same** stub `httpx` object, so `ConnectError` / `ConnectTimeout` / `HTTPStatusError` are one class each suite-wide.
- `test_file_transfer` in isolation still passes; existing stub behaviour (patchable `httpx.put`, `AsyncClient`, `Response`, etc.) is preserved.
- No change to production code behaviour.

**Non-Goals:**
- Making the tests runnable without a venv beyond what the stubs already provide.
- Broad refactor of the stub architecture beyond consolidating the source of truth.
- Any `sys.modules` teardown/restore.

## Decision: one shared stub module (single source of identity)

Introduce `tests/unit/_stubs.py` as the **single authoritative definition** of the fake `httpx` (and `mcp` / `starlette` / `uvicorn`) modules and their exception classes. The install function lives there and is idempotent: if `sys.modules["httpx"]` is already the shared stub, it is reused rather than rebuilt.

```python
# tests/unit/_stubs.py
import sys, types
from typing import Any

class HTTPStatusError(Exception):
    def __init__(self, message="", request=None, response=None):
        super().__init__(message); self.request = request; self.response = response
class ConnectError(Exception): pass
class ConnectTimeout(Exception): pass
# ... Client / AsyncClient / HTTPTransport / Response / put / delete as today ...

def build_httpx_stub() -> types.ModuleType:
    httpx = types.ModuleType("httpx")
    httpx.HTTPStatusError = HTTPStatusError
    httpx.ConnectError = ConnectError
    httpx.ConnectTimeout = ConnectTimeout
    # ... assign the rest ...
    return httpx

def install_import_stubs() -> None:
    """Idempotent: install the ONE shared stub set into sys.modules if absent.
    If httpx is already our shared stub, do nothing (preserves identity)."""
    existing = sys.modules.get("httpx")
    if getattr(existing, "_kirocrew_shared_stub", False):
        return
    httpx = build_httpx_stub()
    httpx._kirocrew_shared_stub = True
    sys.modules["httpx"] = httpx
    # ... mcp / starlette / uvicorn identical to today, all idempotent ...
```

- `test_file_transfer._install_import_stubs()` becomes a thin wrapper that calls `_stubs.install_import_stubs()` (or is replaced by importing it). The try/except stays; only the *definition* of the classes moves out.
- `transport.lifecycle`'s `import httpx` resolves `sys.modules["httpx"]`, which — once any test file has run the install — is the shared stub. Its `ConnectError` is `_stubs.ConnectError`.
- `test_recovery`, `test_network`, `test_server`, `test_openapi` all reach the identical object because the install is idempotent and never rebuilds a second stub with fresh classes.
- `test_recovery._ensure_httpx_exceptions()` is removed (or reduced to calling `_stubs.install_import_stubs()`), so it can no longer synthesize a divergent `ConnectError`. This closes the identity split at its source.

### Ordering guarantee

Because `install_import_stubs()` is idempotent and guarded by the `_kirocrew_shared_stub` marker, the **first** test file to import in discovery order installs the shared stub; every later import — including `lifecycle`'s `import httpx` — resolves that same object. There is no window in which a second `ConnectError` class can be created. This holds regardless of alphabetical discovery order (`test_file_transfer` before `test_network`/`test_recovery`/`test_server`).

### Alternatives considered

- **Patch `httpx.ConnectError` in the stub to be the class `lifecycle` already imported.** Viable but fragile: it requires the stub install to reach into `lifecycle`'s already-bound reference, and creates a chicken-and-egg between lifecycle import and stub install. The shared-module approach makes identity structural rather than a post-hoc patch. *Rejected in favour of the shared module, but acceptable as a fallback if a shared module proves too invasive.*
- **`unittest.mock.patch.dict(sys.modules, ...)` per class.** Rejected — per-class, invasive, and does not cover module-level imports (`lifecycle`'s top-level `import httpx`).
- **Run `test_file_transfer` in a subprocess.** Rejected — process overhead, complicates the runner, and does not help the downstream files that reuse the stub.
- **`tearDownModule` sys.modules snapshot/restore.** Rejected — see the dedicated section above.

## Risks / Trade-offs

- **A real venv with real `httpx` installed.** `install_import_stubs()` only runs in the `ModuleNotFoundError` branch (dependency-free checkout). When real httpx is importable, no stub is installed and identity is trivially consistent (everyone uses real httpx). The shared stub changes nothing there.
- **Attribute surface parity.** The shared stub must expose every attribute the inline stub did (`Client`, `AsyncClient`, `HTTPTransport`, `Response`, `put`, `delete`, plus the exception classes) so `patch.object(server.httpx, "put", ...)` still works. Task 1.5 verifies this.
- **Import-time side effects.** `test_recovery` currently installs the stub as a side effect of `from tests.unit.test_file_transfer import server`. Keeping that import path working (it calls into the shared installer) preserves the existing contract for the downstream files.
