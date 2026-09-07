## Why

Independent review (2026-09-07) found two file-descriptor safety bugs: a double-close hazard in `_write_auth_file()` and `_save_registry()` where `fd = -1` is set inside the `with os.fdopen()` block rather than immediately after the call, and a missing parent-directory fsync in `_write_crew_secret()` meaning the directory entry may be lost on a crash immediately after write.

## What Changes

- `transport/server.py` — fix `_write_auth_file()`: move `fd = -1` sentinel to immediately after `os.fdopen()` succeeds, before the `with` body, to prevent double-close if `os.fdopen()` raises
- `transport/registry.py` — fix `_save_registry()`: same `fd = -1` placement fix
- `transport/server.py` — fix `_write_crew_secret()`: add `os.fsync` on the parent directory after writing, matching the durability guarantee provided by `_save_registry()`
- `tests/unit/` — add tests verifying the fd sentinel placement (or at minimum document the invariant clearly)

## Capabilities

### New Capabilities
- none

### Modified Capabilities
- `registry/durability`: `_save_registry()` fd sentinel fix — closes a double-close hazard on `os.fdopen()` failure

## Impact

- `transport/server.py` — `_write_auth_file()`: one-line fix; `_write_crew_secret()`: add parent dir fsync
- `transport/registry.py` — `_save_registry()`: one-line fix
- `tests/unit/test_lifecycle.py` or `test_server.py` — add coverage for fd safety pattern
