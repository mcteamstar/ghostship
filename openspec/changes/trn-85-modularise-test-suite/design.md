## Context

`tests/unit/test_transport.py` is ~8000 lines covering the full transport stack.
After TRN-71, functions live in five separate modules but tests still patch `server.X`
for everything. TRN-71 used dual-patching as a workaround — this change cleans that up
by aligning test files to module boundaries.

## Decisions

### 1. One test file per module

Each transport module gets its own test file. The split follows import boundaries —
a test goes in `test_X.py` if it primarily tests functions defined in `X.py`.

| Test file | Tests for | Patch target |
|:----------|:----------|:-------------|
| `test_registry.py` | `_load_registry`, `_save_registry`, `_get_crew`, `_touch_crew`, etc. | `transport.registry` |
| `test_podman.py` | `PodmanClient`, `_get_podman`, `_http`, `_get_host_memory_gb`, etc. | `transport.podman` |
| `test_files.py` | `_sign_file_url`, `_handle_file_get`, `_handle_file_put`, `_transfer_upload`, etc. | `transport.files` |
| `test_captain.py` | `_captain_jobs`, `_append_captain_mail`, `_captain_standing_view`, etc. | `transport.captain` |
| `test_lifecycle.py` | `_ensure_crew_running`, `_finish_crew_setup`, `_crew_api_with_recovery`, etc. | `transport.lifecycle` |
| `test_server.py` | MCP tools (`crews`, `launch`, `dispatch`, `pickup`, `steer`, `nuke`, `captain`, `schedule`, `evac`, `supply`), login state machine, routes | `transport.server` + `transport.lifecycle` for internal deps |

### 2. Patch target cleanup

All `patch.object(server, "X")` calls where `X` lives in another module are updated
to `patch.object(<owning_module>, "X")`. Dual-patch workarounds from TRN-71 are
removed — each test patches exactly one module for each name.

### 3. Shared test helpers

Any setup/teardown or mock factories used across multiple test files move to
`tests/unit/helpers.py` (alongside the existing `tests/e2e/helpers.py`).

### 4. Migration strategy

Move tests class-by-class, running `tests/run.sh --unit` after each class migration.
Delete `test_transport.py` only after all classes are migrated and the full suite passes.
This avoids a big-bang rewrite and keeps the suite green throughout.

### 5. test_transport.py deletion

The file is deleted in the final commit of the change, not incrementally, to avoid
having duplicate tests running during migration. Classes are commented out of
`test_transport.py` as they are moved, keeping the file present until the last class
is done.

## Risks

- **Missed tests** — some test classes in `test_transport.py` test interactions between
  modules (e.g. `dispatch()` calling `_crew_api_with_recovery` in lifecycle). These go
  in `test_server.py` since they test MCP tool behaviour, not lifecycle internals.
- **Dual-patch removal breaks tests** — removing dual-patches requires verifying which
  module actually owns the name. The Python introspection script from TRN-71
  (`hasattr(lc, n)`) is the reference for this.
