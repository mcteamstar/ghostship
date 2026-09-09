## Context

`test_file_transfer.py` uses a try/except at module scope to handle environments where `transport.server` can't be directly imported (dependency-free checkout):

```python
try:
    server = importlib.import_module("transport.server")
except ModuleNotFoundError:
    _install_import_stubs()
    server = importlib.import_module("transport.server")
```

`_install_import_stubs()` does `sys.modules["httpx"] = <stub>` (and similarly for `mcp`, `starlette`, `uvicorn`) with no corresponding cleanup. Under `unittest-parallel`, all test modules are imported into the same process before any tests run. If `test_file_transfer` is imported before `test_recovery`, the stub `httpx` is in place when `test_recovery` imports `transport.server`, giving it a stub `httpx.HTTPStatusError` that is not a subclass of the real one — breaking all recovery tests.

## Goals / Non-Goals

**Goals:**
- `run.sh --unit` passes cleanly under the parallel runner
- `test_file_transfer` tests continue to work exactly as before
- No change to production code

**Non-Goals:**
- Refactoring the stub architecture broadly
- Making the tests runnable without a venv (the stubs already handle that)

## Decisions

### Save/restore `sys.modules` at module level

Snapshot the relevant keys from `sys.modules` before `_install_import_stubs()` runs, then restore them in `tearDownModule`. This is the minimal, reversible fix.

```python
_STUB_KEYS = ["httpx", "mcp", "mcp.server", ...]  # all keys _install_import_stubs touches
_original_modules: dict = {}

def setUpModule():
    global _original_modules
    _original_modules = {k: sys.modules.get(k) for k in _STUB_KEYS}

def tearDownModule():
    for k, v in _original_modules.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v
```

The stubs are installed at import time (before `setUpModule` runs), so we need to snapshot the *pre-stub* state. The correct approach: record the original values **before** the try/except block at module load time, and restore in `tearDownModule`.

**Alternative considered:** `unittest.mock.patch.dict(sys.modules, ...)` as a class decorator on each test class. Rejected — more invasive, requires touching each class, and doesn't cover module-level imports that happen after the stub installation.

**Alternative considered:** Run `test_file_transfer` in a subprocess. Rejected — overkill; adds process overhead and complicates the runner.

## Risks / Trade-offs

- If any test in `test_file_transfer` stores a reference to a stub class (e.g. `httpx.HTTPStatusError`) and uses it *after* `tearDownModule` (shouldn't happen — tests don't run after teardown), restore would break it. Risk: none in practice.
- The save must happen before the stubs are installed (at module load), not in `setUpModule` (which runs after import). This means using a module-level variable initialized before the try/except.
