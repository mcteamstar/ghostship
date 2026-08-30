## Context

`tests/unit/test_transport.py` is ~8500 lines. After TRN-71, it contains dual-patch
pairs for every name that moved to a non-server module. TRN-71's dual-patch workaround
kept tests passing but introduced a maintenance burden: the wrong mock gets the alias,
assertions on call counts silently pass against the shadow rather than the real mock,
and future contributors have no obvious signal to follow.

This change migrates each test class to the file matching its module, collapses
dual-patches to single patches, and deletes `test_transport.py`.

## Decisions

### 1. One test file per module

A test class goes in `test_X.py` if it primarily tests functions **defined in** `X.py`.
The governing question is not "which module does the test import from" but "which
module's globals does the function under test read from when it executes."

| Test file | Tests for | Canonical patch target |
|:----------|:----------|:----------------------|
| `test_registry.py` | `_load_registry`, `_save_registry`, `_get_crew`, `_touch_crew`, `_get_crew_schedules`, `_upsert_crew_schedule`, `_remove_crew_schedule`, `_advance_next_fire_at` | `transport.registry` |
| `test_podman.py` | `PodmanClient`, `_get_podman`, `_http`, `_async_http`, `_get_host_memory_gb`, `_wait_for_memory` | `transport.podman` |
| `test_files.py` | `_sign_file_url`, `_sign_upload_url`, `_verify_file_token`, `_handle_file_get`, `_handle_file_put`, `_transfer_upload`, `_TarMemberStream`, `_ResponseChunkReader` | `transport.files` |
| `test_captain.py` | `_append_captain_mail`, `_format_captain_mail`, `_captain_jobs`, `_captain_standing_view`, `_load_order_template`, `_resolve_order_template`, `_mail_count` | `transport.captain` |
| `test_academy.py` | `COMPOSITION_REGISTRY`, `_load_composition_registry`, `_resolve_composition`, `_resolve_manifest_path`, `_resolve_image`, `_load_crew_manifest`, `_manifest_selects`, `_substitute_env_vars`, `_validate_academy`, `_AGENTS_DIR`, `_CREW_REGISTRY_PATH` — absorbs `test_academy_validation.py` and `test_crew_types.py` | `transport.academy` |
| `test_lifecycle.py` | `_ensure_crew_running`, `_finish_crew_setup`, `_crew_api_with_recovery`, `_crew_api`, `_probe_gateway`, `_patch_crew_config`, `_copy_agents`, `_copy_skills`, `_inject_policy`, `_mint_cookie`, `_reconcile_registry` — **not** the academy functions (those moved to `test_academy.py`) | `transport.lifecycle` |
| `test_server.py` | MCP tools (`crews`, `launch`, `dispatch`, `pickup`, `steer`, `nuke`, `captain`, `schedule`, `evac`, `supply`), login state machine (`_handle_login_post`, `_handle_login_get`, `_handle_logout_post`), routes, middleware | `transport.server` for names in server's body; `transport.lifecycle` / `transport.academy` for deps called two levels deep |

### 2. Patch target rule — the call-site principle

The correct patch target depends on **whose namespace resolves the name at call time**:

- If the function under test is defined in `lifecycle.py` → patch `lifecycle.X`
- If the function under test is defined in `server.py` and calls `lifecycle.X` directly
  by name (via `from transport.lifecycle import X`) → patch `server.X` for the
  server-level call, but `lifecycle.X` for any dependency *inside* the lifecycle function

In practice, for `test_lifecycle.py` and `test_captain.py`, patch the owning module
exclusively. For `test_server.py`, the MCP tool bodies call lifecycle functions by name
from server's namespace — patch `server.X` for those call-site mocks. When a server MCP
tool calls `_crew_api_with_recovery` and you want to mock `_http` inside that function,
you must patch `lifecycle._http` (not `server._http`).

**The dual-patch anti-pattern to remove:**
```python
# BEFORE (dual-patch workaround)
patch.object(lifecycle, "_crew_api", side_effect=fake) as api,
patch.object(server,    "_crew_api", side_effect=fake),   # shadow, alias-less
```

**After (single patch on owning module):**
```python
# In test_lifecycle.py or test_captain.py — lifecycle owns _crew_api
patch.object(lifecycle, "_crew_api", side_effect=fake) as api,

# In test_server.py — server's MCP tool body calls _crew_api_with_recovery by name
# from server's namespace; mock at server level to intercept the call
patch.object(server, "_crew_api_with_recovery", return_value=fake_result) as api,
```

### 3. Class inventory

Known test classes in `test_transport.py` and their destinations:

**→ test_registry.py**
- `AdvanceNextFireAtTests`

**→ test_podman.py**
- `MemoryThresholdTests`
- `ConcurrentRestartTests` (partially — the recovery lock tests)

**→ test_files.py**
- `FileTransferSigningTests` (if not already in test_file_transfer.py)

**→ test_captain.py**
- `CaptainStandingOrdersTests`
- `CaptainMailHelperTests`

**→ test_academy.py** (TRN-86 module — absorbs `test_academy_validation.py` and `test_crew_types.py`)
- `TestCrewTypesTool` — tests `transport.academy.COMPOSITION_REGISTRY` via the `compositions` MCP tool
- `TestLaunchCrewType` — tests composition resolution in `launch()`, patches `transport.academy.COMPOSITION_REGISTRY`, `_resolve_composition`, `_resolve_image`
- `CrewTypeRegistryTests` (if present) — tests `_load_composition_registry`, `_resolve_manifest_path`
- All classes from `test_academy_validation.py` — tests `_validate_academy`, already patching `transport.academy`
- All classes from `test_crew_types.py` — tests `_load_crew_manifest`, `_manifest_selects`, `_substitute_env_vars`

**Note on `CopyAgentsMcpTests`:** Stays in `test_lifecycle.py`. It tests `_copy_agents` which is defined in `lifecycle.py`. That function calls `_load_crew_manifest` (academy) and `_substitute_env_vars` (academy) as dependencies — the test patches those at the academy level but the function under test is lifecycle's.

**→ test_lifecycle.py**
- `SetupRegistrationTests`
- `LifecycleRegressionTests`
- `ReconcileRegistryTests`
- `ActiveCrewLimitTests`
- `CopyAgentsMcpTests`
- `LoginLogoutTests`
- `LoginFlowEdgeCaseTests`

**→ test_server.py**
- `TaskOrchestrationTests`
- `PickupTimeoutTests`
- `PersonaValidationTests`
- `TestCrewTypesTool`
- `ResourceJobsTests`
- `CrewsToolTests` (if present)

**Note:** The above is a starting inventory based on known class names. Ghost must
`grep -n "^class " tests/unit/test_transport.py` to get the authoritative list and
verify each class's destination before migrating. Some classes may test interactions
between modules and belong in `test_server.py` even if they touch lifecycle internals.

### 4. Shared helpers

`tests/unit/helpers.py` should receive:
- Any `Mock` factory functions used by multiple test classes (e.g. crew dict builders,
  fake podman constructors)
- Common `setUp`/`tearDown` base classes

Check `test_transport.py` for module-level helper functions before creating stubs.

### 5. Migration strategy

This change is structured for Captain-driven parallel execution:

```
Phase 1 (serial):   Ghost does inventory + stubs + shared helpers (tasks 1.1–1.5)
                    → mails captain "phase 1 done"
Phase 2 (parallel): Captain dispatches 5 Ghosts simultaneously:
    Ghost A → test_registry.py   (tasks 2.1–2.2)
    Ghost B → test_podman.py     (tasks 2.3–2.5)
    Ghost C → test_captain.py    (tasks 2.6–2.8)
    Ghost D → test_lifecycle.py  (tasks 2.9–2.16)  ← largest batch
    Ghost E → test_server.py     (tasks 2.17–2.23)
                    each mails captain "<module> migration done"
Phase 3 (serial):   Captain dispatches cleanup Ghost after all 5 report in
                    (tasks 3.1–3.5)
```

Each Phase 2 Ghost should:
1. Read `design.md` before touching anything — the patch rules are critical
2. Record baseline: `bash tests/run.sh --unit 2>&1 | grep "^Ran"`
3. Migrate one class at a time, run `bash tests/run.sh --unit` after each class
4. Commit after all classes for that module are done
5. Mail `captain@localhost` with subject `trn-85 <module> done` and pass/fail summary

Parallel Ghosts running `bash tests/run.sh --unit` simultaneously is safe — tests are
read-only and don't mutate shared state.

Captain's standing order should: dispatch Phase 1 Ghost on first cycle, wait for
"phase 1 done" mail, then dispatch all 5 Phase 2 Ghosts simultaneously, collect all
5 "<module> migration done" mails, then dispatch the Phase 3 cleanup Ghost, and
escalate to the Admiral on any failure.

### 6. Verification

After all migrations:
```bash
# No stale server patches in module-owned test files
grep -r 'patch.object(server' tests/unit/test_registry.py \
  tests/unit/test_podman.py tests/unit/test_files.py \
  tests/unit/test_captain.py tests/unit/test_lifecycle.py

# Test count unchanged or higher
bash tests/run.sh --unit 2>&1 | grep "^Ran"
```

## Risks

- **Cross-module interaction tests** — `test_server.py` tests MCP tools that call
  lifecycle functions. These tests legitimately patch both `server.X` (the call site)
  and `lifecycle.X` (the dep inside the lifecycle function). This is correct and not a
  dual-patch anti-pattern — the two patches serve different purposes.
- **Class mis-assignment** — if a class is moved to the wrong file, its patches will
  silently pass against the wrong mock. Verify by running the class in isolation and
  checking call count assertions fire correctly.
- **`test_transport.py` left non-empty** — if migration stalls mid-way, there will
  be a period where both old and new files exist. The suite runner picks up all `test_*.py`
  files, so duplicate tests would inflate counts. Monitor with `bash tests/run.sh --unit | grep "^Ran"`.
