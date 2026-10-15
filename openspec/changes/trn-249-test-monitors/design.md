# Design

## Context

`transport/monitors.py` contains three daemon-thread loops (`_schedule_monitor`,
`_idle_monitor`, `_captain_monitor`) and several pure helpers (`_cron_activity_since`,
`_cron_has_enabled_job`, `_note_idle_skip`). The module uses the `bind_lifecycle()`
injection pattern to receive runtime functions from `lifecycle.py` at load time,
breaking the monitors↔lifecycle import cycle. Existing unit tests in
`tests/unit/test_sentinel.py` and partial coverage in `test_monitors.py` (if
present) cover captain-monitor sentinel logic; the schedule and idle loops and all
helpers are untested.

The test suite relies on two conventions established across prior test-coverage
changes (trn-234, trn-236):
1. `FakePodmanClient` from `tests/fakes.py` for container calls — no `Mock()` for Podman.
2. Call-site patching via `unittest.mock.patch.object(monitors, ...)` to replace
   the injected lifecycle globals (`_crew_api`, `_crew_api_with_recovery`,
   `_ensure_crew_running`, `_mint_cookie`) without touching lifecycle itself.

See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**
- Full branch coverage of `_schedule_monitor` iteration logic (due/not-due, disabled, captain-type, gateway disable sync, one-shot teardown, `_ensure_crew_running` failure).
- Full branch coverage of `_idle_monitor` iteration logic (active tasks, cron activity, captain schedule hold, cookie 401 refresh, TOCTOU guard, `_stopping` flag).
- Full branch coverage of `_captain_monitor` iteration logic (sentinel auto-pause, due/not-due, `_ensure_crew_running` failure).
- 100% branch coverage of `_cron_activity_since`, `_cron_has_enabled_job`, `_note_idle_skip`.
- Tests fit in `tests/unit/test_monitors.py` (single file, matches prior trn-234 pattern).
- No new production code changes.

**Non-Goals:**
- Starting or stopping real daemon threads in tests.
- Integration tests against a live container runtime.
- Testing `lifecycle.py` paths not directly invoked from `monitors.py`.

## Decisions

### D-1: Extract single-iteration logic into a synchronous helper

The loops use `while True: time.sleep(...)` which cannot be unit-tested directly
without spawning threads. The approach already established in the codebase for
`test_monitors.py` (trn-234) is to extract the per-cycle body into a separate
function (e.g. `_run_schedule_monitor_tick`) and test it synchronously. If the
real loops already inline their body without a helper, the test class patches
`time.sleep` to a no-op and calls the function directly after monkey-patching
`registry._reg` — the same technique used in `TestScheduleMonitor` in prior art.

Alternative considered: start the thread and use `threading.Event` to signal
completion — rejected because it makes tests flaky and slow, and imports the
entire lifecycle stack.

### D-2: bind_lifecycle injection replaces imports for patchable names

`monitors.py` deliberately does not import `_crew_api`, `_ensure_crew_running`,
etc. at module load; `lifecycle` injects them via `bind_lifecycle()`. Tests call
`monitors.bind_lifecycle(...)` with stub callables before each test, then patch
individual names via `patch.object(monitors, "_crew_api", ...)` as needed. This
mirrors the documented design intent and gives tests precise call-site patching
without modifying the production module.

### D-3: FakeHTTPModule for `_http.get` calls in the idle monitor

`_idle_monitor` calls `_http.get(...)` from `transport.podman`. Tests patch
`monitors._http` with a simple fake that returns scripted `MockResponse` objects
(with `.status_code` and `.json()`). The same pattern was used in trn-234 for
`_crew_api`. No real network calls.

### D-4: Registry patching via `_block_registry_io` autouse fixture

The autouse `_block_registry_io` fixture in `conftest.py` already blocks
`_load_registry` / `_save_registry`. Tests set `registry._reg` directly for
state, and use `with registry:` blocks patched to a no-op file I/O for the
save/load cycle. No changes needed to `conftest.py`.

### D-5: `_idle_skip_reasons` state isolation between tests

`_note_idle_skip` writes to the module-level `_idle_skip_reasons` dict in
`monitors.py`. Each test that touches this function must clear the dict in
setUp/tearDown (`monitors._idle_skip_reasons.clear()`) to prevent cross-test
pollution. The test class documents this explicitly.

## Risks / Trade-offs

- [Risk: monitors._reg access] `_idle_monitor` and `_schedule_monitor` both
  access `registry._reg` directly. The `_block_registry_io` fixture only patches
  the `_load_registry` / `_save_registry` I/O calls; tests must also pre-populate
  `registry._reg` with synthetic state. → Mitigation: setUp clears and seeds the
  dict before each test, matching the `TestScheduleMonitor` pattern in trn-234.

- [Risk: bind_lifecycle re-entrancy] If a test file imports `transport.lifecycle`
  (e.g. via a transitive import), `bind_lifecycle()` is called automatically with
  real function objects, overwriting test-installed stubs. → Mitigation: all
  monitor tests import `transport.monitors` directly, not `transport.lifecycle`.
  The test class setUp always calls `monitors.bind_lifecycle(...)` with stubs
  after import to guarantee controlled state.

- [Risk: captain monitor imports server at call time] `_captain_monitor` does
  `from transport.server import _steer_captain_checkin` lazily. Tests that test
  the captain monitor must either stub `transport.server` in `sys.modules` or
  patch the lazy import site. → Mitigation: patch `monitors._captain_monitor`'s
  inner import using `patch("transport.server._steer_captain_checkin")` or by
  pre-installing a stub in `sys.modules["transport.server"]` in setUp.
