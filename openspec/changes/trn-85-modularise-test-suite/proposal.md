## Problem

TRN-71 split `transport/server.py` into five modules: `registry.py`, `podman.py`,
`files.py`, `captain.py`, `lifecycle.py`. The test suite did not follow —
`tests/unit/test_transport.py` remains a single ~8500-line file covering all of those
modules plus the MCP tool layer in server.py.

This creates two concrete problems:

**1. Patch targets are structurally wrong.**

Python's `unittest.mock.patch.object(module, "name")` replaces the named attribute on
that module object. When a function is extracted to `lifecycle.py`, its body resolves
names from `lifecycle`'s module globals — not `server`'s. Patching `server._http` after
extraction has no effect on `lifecycle._crew_api_with_recovery`, which looks up `_http`
in `lifecycle`'s namespace.

TRN-71 worked around this with **dual-patching**: every moved name gets patched on
*both* modules simultaneously:

```python
patch.object(lifecycle, "_crew_api", side_effect=fake) as api,
patch.object(server,    "_crew_api", side_effect=fake),   # shadow
```

The lifecycle patch is the one that matters (it's where the function executes). The
server patch keeps server's binding consistent for any MCP tool that calls the name
directly from server's own body. The alias (`as api`) goes on the lifecycle patch — the
mock that actually records calls.

This works but is verbose, fragile, and makes the test intent opaque. Every future
test written in this state has to reproduce the dual-patch pattern or silently break.

**2. Navigation and ownership are unclear.**

An 8500-line test file has no structure that maps to the module layout. Finding tests
for `_ensure_crew_running` requires searching. Understanding which tests would break if
`registry.py` changed requires reading the whole file. The mismatch between the five-module
source layout and the one-file test layout will grow worse as tests are added.

## Proposal

Split `tests/unit/test_transport.py` into one test file per transport module:

- `tests/unit/test_registry.py`
- `tests/unit/test_podman.py`
- `tests/unit/test_files.py`
- `tests/unit/test_captain.py`
- `tests/unit/test_lifecycle.py`
- `tests/unit/test_server.py` — MCP tool handlers, routes, login state machine

Each file patches only its own module. Dual-patch pairs collapse to single patches on
the canonical module. The `as alias` confusion disappears — there is only one mock.

The existing `test_self_healing.py`, `test_academy_validation.py`, `test_crew_types.py`,
and `test_file_transfer.py` stay as-is (they are already well-scoped and their patch
targets are unambiguous).

`test_transport.py` is deleted once all classes are migrated and the suite passes.

## Out of scope

- Adding new test coverage (that's TRN-84)
- Changing test semantics or fixing pre-existing failures
- Restructuring the non-transport test files
- Fixing the pre-existing `croniter` missing-dependency failure in `test_cron_branch`
  (that test passes in the crew environment where `requirements.txt` is installed)
