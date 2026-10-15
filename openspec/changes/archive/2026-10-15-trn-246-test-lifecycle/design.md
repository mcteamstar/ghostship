## Context

See `proposal.md – Why` for motivation. Key structural facts:

- `transport/lifecycle.py` (~3,200 lines) is the largest transport module and the only one with no dedicated unit test file.
- The actual launch concurrency logic lives in `transport/launcher.py` (`CrewLauncher`), which `lifecycle.py` delegates to via `_launcher.ensure_running` and `_launcher.finish_setup`. Testing the concurrency paths therefore means exercising `CrewLauncher` directly.
- `_cleanup_crew` is a pure Podman-side teardown helper used by both partial cleanup (launch failure) and full teardown (`nuke`). It is self-contained and straightforward to test in isolation.
- `_secret_identifier` is a pure function with no I/O — trivial to test.
- The existing test suite (`tests/unit/`) uses:
  - `FakePodmanClient` from `tests/fakes.py` — full `ContainerRuntime` fake with scripted responses and a `calls` log.
  - `conftest.py` — installs httpx/mcp/starlette/uvicorn stubs via `_install_transport_stubs()` and patches `_load_registry`/`_save_registry` to block disk I/O. Both run automatically for all unit tests.
  - `unittest.mock.patch` alongside the fake, to isolate module-level globals (e.g., `lifecycle._startup_events`).

```
tests/unit/
├── conftest.py           ← stubs + registry I/O block (autouse)
├── test_config.py
├── test_login.py
├── test_registry_lock.py
├── test_sentinel.py
└── test_lifecycle.py     ← NEW (this change)
```

## Goals / Non-Goals

**Goals:**
- Cover `_cleanup_crew` (best-effort teardown, all 4 resource types, fault isolation).
- Cover `CrewLauncher.ensure_running` (happy path, leader/waiter concurrency, `_NUKED_DURING_RESTART` sentinel, leader exception propagation, active-limit gate, memory gate).
- Cover the state-transition graph: `launching→running`, `running→stopped`, `stopped→running`, `running→removed`.
- Cover `_secret_identifier` (correctness, uniqueness, determinism).
- Exercise `CrewLauncher._check_active_limit` (stale-entry correction, limit enforcement, disabled=0).
- Exercise `CrewLauncher._check_memory_gate` (blocking, disabled=0).

**Non-Goals:**
- No coverage of `_finish_crew_setup` / `_launcher.finish_setup` in this change — that involves network waits, PTY exec, cookie minting and a long setup chain that warrants its own follow-on ticket.
- No coverage of `_reconcile_registry`, `_idle_monitor`, login flows, or schedule machinery — those are tracked in `transport-test-coverage` separately.
- No changes to production code.

## Decisions

**D1: Test `CrewLauncher` directly, not via the `lifecycle._ensure_crew_running` wrapper.**

The wrapper is a one-liner that calls `_launcher.ensure_running`. Testing through it adds nothing — the interesting logic is in `CrewLauncher`. Instantiate `CrewLauncher` directly in tests, injecting a `FakePodmanClient` and a mock `CrewRegistry`.

*Alternative: patch `lifecycle._launcher`* — this works but requires more setup per test and makes the test class the launcher's collaborator rather than the caller; direct instantiation is cleaner.

**D2: Use `threading.Thread` for concurrency tests, not `concurrent.futures`.**

The leader/waiter pattern uses `threading.Event` internally. Using `threading.Thread` directly lets tests set pre-conditions before the threads start and inspect the event state after they finish. `concurrent.futures.ThreadPoolExecutor` adds no benefit here.

**D3: Patch module-level constants via `unittest.mock.patch` for gate tests.**

`_check_active_limit` reads `GA_MAX_ACTIVE_CREWS` from `lifecycle`. Patching `transport.lifecycle.GA_MAX_ACTIVE_CREWS` (and similarly `GA_MIN_FREE_MEM_GB` for the memory gate) isolates gate tests without touching `Config`. This is the same pattern used in existing test modules.

**D4: For registry interactions in `CrewLauncher`, use a real `CrewRegistry` instance backed by `_load_registry`/`_save_registry` patches from `conftest.py`.**

The `conftest.py` autouse fixture already patches `_load_registry` to return `{"crews": {}}` and `_save_registry` to a no-op. Tests that need a populated registry pre-seed `registry._reg["crews"]` directly before exercising `ensure_running`.

**D5: Test `_cleanup_crew` by scripting `FakePodmanClient` to raise on specific calls.**

`FakePodmanClient` raises `RuntimeError` for unscripted `container_inspect` / `container_archive_get` calls but silently no-ops for `container_stop`, `container_remove`, and `volume_remove`. To test fault isolation (step X fails, remaining steps still run), subclass or monkey-patch the fake to raise on the specific call being tested. A minimal approach: override the relevant method on the instance before calling `_cleanup_crew`.

**D6: Separate test classes per logical area.**

Mirrors the existing style in `test_sentinel.py` and `test_login.py`:

```
TestCleanupCrew            ← _cleanup_crew teardown + fault isolation
TestEnsureRunning          ← CrewLauncher.ensure_running happy path + nuked-during-restart
TestEnsureRunningConcurrency ← leader/waiter, generation counter, leader exception propagation
TestActiveLimit            ← CrewLauncher._check_active_limit
TestMemoryGate             ← CrewLauncher._check_memory_gate
TestStateTransitions       ← end-to-end state graph driven through FakePodmanClient
TestSecretIdentifier       ← _secret_identifier pure-function tests
```

## Risks / Trade-offs

- **[Risk] `ensure_running` imports lazily inside the method.** The method uses `try/except ModuleNotFoundError` to import from `lifecycle` and `registry`. In test context the `transport.lifecycle` package path must be on `sys.path`. The existing conftest already handles this (it imports from `transport.*` successfully). Mitigation: verify at PR time that `from transport.launcher import CrewLauncher` resolves cleanly in the test environment.

- **[Risk] Concurrency tests are timing-sensitive.** Leader/waiter tests use `threading.Event.wait(timeout=...)`. A very slow test machine could cause the event to time out before the leader fires it, producing a false failure. Mitigation: use generous timeouts (5 s) and assert on outcome, not timing.

- **[Risk] `_check_memory_gate` calls `_wait_for_memory` which polls.** Patching `GA_MIN_FREE_MEM_GB` alone is insufficient; `_wait_for_memory` internally calls `system_info()` in a polling loop. Mitigation: also patch `lifecycle._wait_for_memory` to return the scripted value immediately, avoiding a real polling loop in tests.

## Migration Plan

No production code changes. Rollout:
1. Create `tests/unit/test_lifecycle.py`.
2. Run `pytest tests/unit/` locally to confirm the new tests pass and existing tests are unaffected.
3. Submit PR — CI runs the unit suite automatically via `.github/workflows/test.yml`.
