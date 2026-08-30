## Prerequisites

- [x] 0.1 TRN-71 fully landed — `transport/lifecycle.py` committed, all 421 unit tests passing
- [x] 0.2 TRN-86 fully landed — `transport/academy.py` extracted from `lifecycle.py`; test target for academy functions is `test_academy.py` not `test_lifecycle.py`

## 0. Captain standing order

The Admiral sets up Captain with a standing order that drives the three phases. Captain dispatches Ghosts, collects their mail, and advances phases automatically.

- [ ] 0.2 Launch a crew, seed with `release/0.2.1`, and set Captain's standing order:
  - **Phase 1:** On first cycle (no "phase 1 done" mail yet), dispatch Ghost to do inventory + stubs (tasks 1.1–1.5). Ghost mails `captain@localhost` with subject `trn-85 phase 1 done` when complete.
  - **Phase 2:** When "phase 1 done" received and no Phase 2 Ghosts dispatched yet, dispatch 5 Ghosts simultaneously — one per module (tasks 2.x). Each Ghost mails `captain@localhost` with subject `trn-85 <module> done`.
  - **Phase 3:** When all 5 `trn-85 * done` mails received, dispatch a single Ghost for cleanup (tasks 3.1–3.5). Ghost mails `captain@localhost` with subject `trn-85 cleanup done`.
  - **On failure:** Any Ghost that reports a failure → escalate to `admiral@localhost` with the failing module and error summary.

## 1. Inventory and setup

- [x] 1.1 Get full class list: `grep -n "^class " tests/unit/test_transport.py` — note each class name and line number
- [x] 1.2 For each class, determine destination file using the call-site principle from design.md §2 and the class inventory in design.md §3
- [x] 1.3 Run the ownership introspection to confirm which names need lifecycle vs server patches:
  ```python
  import transport.lifecycle as lc
  import transport.server as srv
  from unittest.mock import patch, Mock
  needs_lifecycle = []
  for name in dir(lc):
      if not name.startswith('_'): continue
      if hasattr(srv, name):
          fake = Mock()
          with patch.object(srv, name, fake):
              if getattr(lc, name) is not fake:
                  needs_lifecycle.append(name)
  print(needs_lifecycle)
  ```
- [x] 1.4 Create `tests/unit/helpers.py` — move shared mock factories and setUp helpers from `test_transport.py` (look for module-level functions and base classes used by multiple test classes)
- [x] 1.5 Create stub files with correct imports:
  - `tests/unit/test_registry.py` — `import transport.registry as registry`
  - `tests/unit/test_podman.py` — `import transport.podman as podman`
  - `tests/unit/test_files.py` — `import transport.files as files_mod`
  - `tests/unit/test_captain.py` — `import transport.captain as captain_mod`
  - `tests/unit/test_academy.py` — `import transport.academy as academy` (TRN-86 module: `COMPOSITION_REGISTRY`, `_load_composition_registry`, `_resolve_composition`, `_resolve_manifest_path`, `_resolve_image`, `_load_crew_manifest`, `_manifest_selects`, `_substitute_env_vars`, `_validate_academy`, `_AGENTS_DIR`, `_CREW_REGISTRY_PATH` — absorbs `test_academy_validation.py` and `test_crew_types.py`)
  - `tests/unit/test_lifecycle.py` — `import transport.lifecycle as lifecycle` (lifecycle proper: `_ensure_crew_running`, `_finish_crew_setup`, `_copy_agents`, `_copy_skills`, etc. — **not** academy functions)
  - `tests/unit/test_server.py` — `import transport.server as server; import transport.lifecycle as lifecycle; import transport.academy as academy`

## 2. Migrate test classes

For each class: move → update patch targets → delete from test_transport.py → run suite → commit.

**Patch rule recap:**
- Function defined in `lifecycle.py` → patch `lifecycle.X`; lifecycle gets `as alias`
- MCP tool in `server.py` calling lifecycle functions → patch `server.X` for the
  call-site intercept; patch `lifecycle.X` for any dep *inside* the lifecycle function
- Remove all dual-patch pairs where both targets do the same thing; keep legitimate
  two-level patches (server call site + lifecycle internal dep)

### → test_registry.py

- [x] 2.1 Migrate `AdvanceNextFireAtTests` → `test_registry.py`; patch via `transport.registry`
- [x] 2.2 Commit: `refactor(trn-85): migrate registry tests to test_registry.py`

### → test_podman.py

- [x] 2.3 Migrate `MemoryThresholdTests` → `test_podman.py`; patch via `transport.podman` (actual classes: `TestMemoryGate`→`MemoryGateTests`, `TestMemoryCache`→`MemoryCacheTests`, `TestCrewsMemoryField`→`CrewsMemoryFieldTests`)
- [x] 2.4 Migrate any podman/http recovery tests → `test_podman.py` (n/a — no standalone podman http/recovery classes; `_http`/`_async_http` paths live in server-bound `ProxyHandlerTests`/`PickupTimeoutTests` → test_server.py)
- [x] 2.5 Commit: `refactor(trn-85): migrate podman tests to test_podman.py`

### → test_captain.py

- [x] 2.6 Migrate `CaptainStandingOrdersTests` → `test_captain.py`; patch via `transport.captain` and `transport.lifecycle` (captain calls lifecycle's `_crew_api_with_recovery`)
- [x] 2.7 Migrate `CaptainMailHelperTests` (or equivalent) → `test_captain.py` (no separate class — the `_format_captain_mail`/`_append_captain_mail`/`_mail_count` helper tests are methods within `CaptainStandingOrdersTests`, migrated together)
- [x] 2.8 Commit: `refactor(trn-85): migrate captain tests to test_captain.py`

### → test_academy.py (requires TRN-86 ✅ done)

- [x] 2.9a Migrate the following to `test_academy.py`, all patching via `transport.academy`:
  - `TestLaunchCrewType` from `test_transport.py` — composition resolution tests; patch `transport.academy.COMPOSITION_REGISTRY`, `_resolve_composition`, `_resolve_image` (the dual-patches on lifecycle/server for these are now wrong; collapse to single `transport.academy` patches)
  - `TestCrewTypesTool` from `test_transport.py` — `compositions` MCP tool; patch `transport.academy.COMPOSITION_REGISTRY`
  - Any `CrewTypeRegistryTests` — `_load_composition_registry`, `_resolve_manifest_path`
  - All classes from `test_academy_validation.py` — already patching `transport.academy` correctly (no changes needed, just move/import)
  - All classes from `test_crew_types.py` — `_load_crew_manifest`, `_manifest_selects`, `_substitute_env_vars`; update any remaining lifecycle/server patches to `transport.academy`
  - **Note on `CopyAgentsMcpTests`:** stays in `test_lifecycle.py` — it tests `_copy_agents` (lifecycle), which calls academy functions as deps. The academy patches in `_run()` helper (`_load_crew_manifest`, `Path`, logger) are correct as written after TRN-86 test fixes.
- [x] 2.9b Commit: `refactor(trn-85): migrate academy tests to test_academy.py`

### → test_lifecycle.py

- [ ] 2.9 Migrate `SetupRegistrationTests` → `test_lifecycle.py`; patch via `transport.lifecycle`
- [ ] 2.10 Migrate `LifecycleRegressionTests` → `test_lifecycle.py`
- [ ] 2.11 Migrate `ReconcileRegistryTests` → `test_lifecycle.py`
- [ ] 2.12 Migrate `ActiveCrewLimitTests` → `test_lifecycle.py`; note `_wait_gateway` and `_patch_crew_config` need `lifecycle` patches
- [ ] 2.13 Migrate `CopyAgentsMcpTests` → `test_lifecycle.py`; note `transport.lifecycle.Path` is the right patch target (not `transport.server.Path`), and lifecycle's logger needs the warning handler
- [ ] 2.14 Migrate `LoginLogoutTests` → `test_lifecycle.py`; note `_nuke_login_container` is in lifecycle but called from server's `_handle_login_*` bodies — patch `server._nuke_login_container` for the assertion
- [ ] 2.15 Migrate `LoginFlowEdgeCaseTests` → `test_lifecycle.py`
- [ ] 2.16 Commit: `refactor(trn-85): migrate lifecycle tests to test_lifecycle.py`

### → test_server.py

- [ ] 2.17 Migrate `TaskOrchestrationTests` → `test_server.py`; these test MCP tools (`dispatch`, `steer`) — patch `server.X` for call-site mocks, `lifecycle.X` for internal deps
- [ ] 2.18 Migrate `PickupTimeoutTests` → `test_server.py`; `_crew_api` is called via `_crew_api_with_recovery` in lifecycle — patch `lifecycle._crew_api as api`
- [ ] 2.20 Migrate `PersonaValidationTests` → `test_server.py`
- [ ] 2.21 Migrate `ResourceJobsTests` → `test_server.py`
- [ ] 2.22 Migrate any remaining MCP tool test classes → `test_server.py`
- [ ] 2.23 Commit: `refactor(trn-85): migrate server/MCP tool tests to test_server.py`

## 3. Cleanup

- [ ] 3.1 Confirm `test_transport.py` is empty (only imports and comments remain)
- [ ] 3.2 Run `bash tests/run.sh --unit 2>&1 | grep "^Ran"` — record count; must match or exceed pre-migration count (421)
- [ ] 3.3 Delete `tests/unit/test_transport.py`
- [ ] 3.4 Run full suite: `bash tests/run.sh` — all pass
- [ ] 3.5 Commit: `refactor(trn-85): delete test_transport.py — migration complete`

## 4. Verification

- [ ] 4.1 No stale server patches in module-owned files:
  ```bash
  grep -rn 'patch.object(server' tests/unit/test_registry.py \
    tests/unit/test_podman.py tests/unit/test_files.py \
    tests/unit/test_captain.py tests/unit/test_lifecycle.py
  ```
  Should return nothing (or only legitimate cross-module patches with a comment explaining why).
- [ ] 4.2 Test count at or above 421: `bash tests/run.sh --unit 2>&1 | grep "^Ran"`
- [ ] 4.3 No dual-patch pairs remain where both patches target the same logical name:
  ```bash
  grep -A1 'patch.object(lifecycle' tests/unit/test_server.py | \
    grep 'patch.object(server'
  ```
  Any hits should be reviewed — legitimate if the two patches serve different purposes
  (call-site vs internal dep), a bug if they duplicate each other.

## 5. Nits from TRN-71 code review (fix during migration)

These were flagged by Banshee during the TRN-71 review. Non-blocking individually but
worth cleaning up as part of TRN-85's patch cleanup pass.

- [ ] 5.1 `transport/podman.py` line 12 — remove unused `import select` (dead import)
- [ ] 5.2 `transport/podman.py` — `server.py` imports `_host_memory_cache` by name, but
  this global is reassigned inside `_get_host_memory_gb_cached`, so server's binding
  captures the initial `None` and never sees cache updates. Verify server.py isn't
  relying on a stale binding; if it is, change the import to read through the module
  (`podman._host_memory_cache`) or call `_get_host_memory_gb_cached()` instead.
- [ ] 5.3 `transport/registry.py` — `_advance_next_fire_at` has two untested branches:
  the malformed-cron `+60s` fallback and the unknown-schedule-type → `_NEVER_FIRE_AT`
  path. Add direct tests for these in `test_registry.py` during migration.
- [ ] 5.4 `transport/podman.py` — memory helpers (`_get_host_memory_gb`,
  `_get_host_memory_gb_cached`) have no direct unit tests. Add basic coverage in
  `test_podman.py` during migration (mock `system_info()`).
