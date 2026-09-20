## Why

`_inject_git_identity` in `lifecycle.py` is a documented no-op stub that is never called in production code. It exists only as a dead symbol that misleads readers into thinking git identity injection requires a container exec step (it doesn't — git vars are injected at container creation time via `env=`). Removing it eliminates confusion and reduces maintenance surface.

## What Changes

- Delete `_inject_git_identity` function from `transport/lifecycle.py` (L1715–1716)
- Remove the explanatory comment block at the former call site (~L1903–1906) that explains the removal — now unnecessary since the function no longer exists
- Delete two test methods in `tests/unit/test_server.py` that verify the no-op behaviour:
  - `test_inject_git_identity_is_noop_does_not_exec`
  - `test_finish_crew_setup_completes_successfully_without_inject_git_identity`

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

_(none — pure dead-code removal, no externally observable behaviour changes)_

## Impact

- `transport/lifecycle.py` — 2 lines deleted
- `tests/unit/test_server.py` — 2 test methods deleted
- No API changes, no config changes, no behaviour changes
