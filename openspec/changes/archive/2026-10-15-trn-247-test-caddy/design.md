# Design

## Context

`transport/caddy.py` is a 320-line module with two main objects: the
module-level port pool (`_dashboard_ports_in_use: set[int]`) and
`CaddyPortal`, the class that wraps the Caddy admin API. The module imports
only stdlib, `httpx2`, `transport.config`, and `transport.registry` — making
it straightforwardly importable in a no-Caddy, no-Podman test environment given
the stubs already installed by `tests/unit/conftest.py`.

The existing unit suite (see `tests/unit/conftest.py`) establishes these
conventions:
- `_install_transport_stubs()` installs `httpx2` and other stubs at session
  scope; `caddy.py` uses `httpx2 as httpx`, so it resolves the same stub.
- Tests avoid patching import paths; instead they use `unittest.mock.patch`
  on module-level names or pass explicit instances.
- `@pytest.fixture(autouse=True) _block_registry_io` is already in place and
  will apply to the new test file automatically.

The module-level `_dashboard_ports_in_use` set is a process-global singleton.
Tests that mutate it must clean it up afterwards to avoid cross-test leakage.

## Goals / Non-Goals

**Goals:**
- Cover every branch in `CaddyPortal.allocate_port`, `release_port`,
  `register_crew`, `deregister_crew` (happy paths, edge cases, error paths)
- Cover the module-level thin wrappers (`_allocate_dashboard_port`,
  `_release_dashboard_port`, `_caddy_register_crew`, `_caddy_deregister_crew`)
- Cover `_caddy_admin_url()` and the `CaddyPortal` constructor
- Run under the existing `pytest tests/unit/` invocation with no new deps

**Non-Goals:**
- Testing live Caddy connectivity
- Retesting `_validate_caddy_tls_mode` (already covered in `test_config.py`)
- Integration or e2e tests for the Caddy routing pipeline

## Decisions

### D1: Use `unittest.mock.patch` on `httpx2.put` / `httpx2.delete`

The `CaddyPortal` methods call `httpx.put` and `httpx.delete` directly at
module scope (the module does `import httpx2 as httpx`). Patching the
module-level references (`transport.caddy.httpx.put`, etc.) via
`unittest.mock.patch` is the cleanest approach — it avoids threading a fake
HTTP client through the constructor (which the class does not currently accept)
and does not require changing any production code.

Alternative considered: constructor injection of an HTTP client. This would be
cleaner long-term but requires a production code change outside this ticket's
scope.

### D2: `_dashboard_ports_in_use` isolation via setUp/tearDown

Because the port pool is a module-level set, each test class that exercises
port allocation clears it in `setUp` and restores it (or clears again) in
`tearDown`. This is preferable to monkeypatching the set reference, which
would break the module's own references.

### D3: `time.sleep` patched out in retry tests

`CaddyPortal.register_crew` sleeps up to 3 seconds between retries. Tests that
exercise the retry path patch `transport.caddy.time.sleep` to a no-op so the
suite stays fast.

### D4: One test class per behavioural group

Three `unittest.TestCase` subclasses:
- `TestCaddyPortalPortPool` — allocation and release
- `TestCaddyPortalRegisterCrew` — `register_crew` (config generation, routing)
- `TestCaddyPortalDeregisterCrew` — `deregister_crew` (HTTP codes, error paths)

Plus one small class `TestCaddyModuleLevelHelpers` covering the wrappers,
`_caddy_admin_url`, and constructor field wiring.

This mirrors the `TestConstants` / `TestConfigParsing` split already used in
`test_config.py`.

### D5: No new conftest fixtures

All test doubles needed (mock HTTP responses, port-pool state) are either
local to each test method or set up in `setUp`. Adding global fixtures would
couple this file to `conftest.py` unnecessarily.

## Risks / Trade-offs

- **Module global state** — `_dashboard_ports_in_use` is shared across the
  process. Any test that leaks a dirty port set will cause flaky allocation
  tests in other files if pytest ever runs them in the same process. Mitigation:
  all test classes that touch the pool clear it in both `setUp` and `tearDown`.
- **Retry timing** — patching `time.sleep` means retry timing is not tested.
  The sleep durations are `2**attempt` (0, 1, 2 s), which is trivially correct
  from inspection; timing is not a useful unit-test target here.
- **httpx2 stub coverage** — the existing conftest stub's `put` returns a
  `Response(200)` by default. Tests that need other status codes will
  `unittest.mock.patch` the stub's method for that test scope. No changes to
  `conftest.py` are needed.

## Migration Plan

1. Ghost creates `tests/unit/test_caddy.py` per tasks.md
2. Run `pytest tests/unit/test_caddy.py -v` to verify all pass
3. Run `pytest tests/unit/` to verify no regressions in existing tests
4. Commit; no deployment step (test-only change)
