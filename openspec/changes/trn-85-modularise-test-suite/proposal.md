## Problem

TRN-71 split `transport/server.py` into five modules: `registry.py`, `podman.py`,
`files.py`, `captain.py`, `lifecycle.py`. The test suite did not follow — `tests/unit/test_transport.py`
remains a single ~8000-line file covering all of those modules plus the MCP tool layer.

This creates two concrete problems:

1. **Patch targets are wrong.** Functions that moved to `lifecycle.py` are patched via
   `server.X` in some tests, which doesn't affect `lifecycle.X` (the actual binding the
   function uses). TRN-71 worked around this with dual-patching (`server.X` + `lifecycle.X`),
   which is brittle and hard to maintain.

2. **Navigation and ownership are unclear.** An 8000-line test file with no internal
   structure makes it hard to find tests for a specific module, and makes it obvious which
   tests belong to which module.

## Proposal

Split `tests/unit/test_transport.py` into one test file per transport module, each patching
its own module's names directly:

- `tests/unit/test_registry.py`
- `tests/unit/test_podman.py`
- `tests/unit/test_files.py`
- `tests/unit/test_captain.py`
- `tests/unit/test_lifecycle.py`
- `tests/unit/test_server.py` — MCP tool handlers, routes, login state machine

The existing `test_self_healing.py`, `test_academy_validation.py`, `test_crew_types.py`,
and `test_file_transfer.py` stay as-is (they are already well-scoped).

All dual-patch workarounds introduced in TRN-71 are cleaned up as part of the split —
each test patches the canonical module directly.

`test_transport.py` is deleted once all tests are migrated and passing.

## Out of scope

- Adding new test coverage (that's TRN-84 territory)
- Changing test semantics or fixing pre-existing failures
- Splitting the non-transport test files
