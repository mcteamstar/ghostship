## Context

See proposal.md — Why. Three critical paths in `transport/server.py` have zero or
inadequate test coverage: `_reconcile_registry`, `_idle_monitor`, and
`_finish_crew_setup`. The existing test file (`test_transport.py`) uses custom mock
classes (`SetupPodman`, `GitDiffPodman`, `CookieHeaders`) and `unittest.mock.patch`
for isolation. Additionally, the code review identified three concurrency bugs that
tests should expose and fixes should address.

trn-19 (memory-aware spawn) is now planned and its idle_monitor scope is settled:
trn-19 adds a memory gate to `_ensure_crew_running` but does NOT change
`_idle_monitor`'s logic. Tests written here remain valid after trn-19 lands.

## Goals / Non-Goals

**Goals:**
- Full branch coverage for `_reconcile_registry`, `_idle_monitor`, `_finish_crew_setup`
- Edge-case tests for PTY login flow (`_handle_login_post`)
- Concurrency correctness test for `_handle_login_get` guard clearing
- Expose and fix the `_idle_monitor` 401 path (needs cookie refresh, not silent stop)
- Expose and fix `_reconcile_registry` stale-snapshot write-back race
- Expose and fix `_handle_login_get` guard-clear ordering gap
- Partition the test suite into Podman-dependent and pure unit tests so it runs safely inside crew containers

**Non-Goals:**
- Changing `_idle_monitor` scope or responsibilities (settled by trn-19)
- Integration tests against a real Podman socket
- Refactoring the methods under test beyond minimal fixes
- Testing `_ensure_crew_running` memory gate (that's trn-19)

## Decisions

### 1. Test isolation via mock PodmanClient subclasses

**Choice:** Follow the existing `test_transport.py` pattern — define purpose-built
mock classes (e.g., `ReconcilePodman`, `IdleMonitorPodman`) that record calls and
return configurable responses.

**Alternatives considered:**
- `unittest.mock.MagicMock` for everything — rejected because the existing tests
  already use custom mocks for readability and the type signatures help catch
  misuse at write time.
- pytest fixtures — rejected because the test file already uses `unittest.TestCase`.

**Rationale:** Consistency with existing test patterns minimizes reviewer confusion.

### 2. Single iteration testing for _idle_monitor

**Choice:** Patch the `while True` loop to run exactly once (break after first
iteration), then assert side effects.

**Alternatives considered:**
- Running the thread with a short timeout — fragile timing dependency.
- Extracting a `_idle_monitor_tick()` function — cleaner but requires modifying
  production code (non-goal for this change beyond the three concurrency fixes).

**Rationale:** Patching `time.sleep` to raise `StopIteration` (caught by test
harness) gives deterministic single-iteration coverage without touching production
code structure.

### 3. _finish_crew_setup ordering verification

**Choice:** Wrap each setup helper (`_inject_auth`, `_patch_crew_config`,
`_copy_agents`, etc.) with a `side_effect` that appends to an ordered list.
Assert the list matches the required sequence.

**Rationale:** This catches permutation bugs that a "did it succeed?" test misses.

### 4. Concurrency fix: _handle_login_get guard clear

**Choice:** The existing code already clears `_login_pending` after nuking the
container. The fix ensures the lock is held across the entire clear operation
(it already is). The test verifies this by interleaving a concurrent POST attempt
between the nuke and the clear — the POST must get 409.

### 5. Concurrency fix: _reconcile_registry stale snapshot

**Choice:** The write-back already re-reads under the lock. The fix adds a guard:
`if cid in reg["crews"]` before applying updates. This prevents resurrecting a
crew that was deleted between snapshot and write-back.

**Rationale:** Minimal fix — one `if` guard. The existing code structure (snapshot →
release → per-crew work → re-acquire → merge) is sound; it just lacks the existence
check.

### 6. Concurrency fix: _idle_monitor 401 path

**Choice:** When `/api/spawn` or `/api/crons` returns 401, attempt `_mint_cookie`
for that crew. On success, retry the request with the new cookie. On failure, skip
the crew (fail-open) for this cycle.

**Alternatives considered:**
- Call `_refresh_cookie` (the full recovery wrapper) — too heavy; it can trigger a
  container restart, which is inappropriate for a background monitor.
- Stop the crew anyway — wrong; a 401 likely means the cookie expired while the
  crew is active, and stopping it would kill running work.

**Rationale:** The idle monitor's job is conservative — it should only stop crews it
is confident are idle. A 401 means "can't check," not "nothing is running."

### 7. Test suite portability: @skipUnless guards

**Choice:** Decorate all test classes/methods that require a real Podman socket
with `@unittest.skipUnless(shutil.which("podman"), "requires podman")`. Add a
comment block at the top of `test_transport.py` listing which classes are
Podman-dependent.

**Alternatives considered:**
- Separate test files (`test_transport_unit.py` / `test_transport_integration.py`)
  — cleaner split but requires renaming all existing imports and CI config.
- Environment variable flag (`TEST_INTEGRATION=1`) — less discoverable than a
  standard `skipUnless` that auto-detects the environment.

**Rationale:** `shutil.which("podman")` is zero-config — it works correctly on both
a developer's Mac and inside a crew container without any manual setup. The comment
block at the top of the file makes the split immediately visible to anyone running
the suite for the first time.

## Risks / Trade-offs

- **[Single-iteration mock may miss timing bugs]** → Accepted. Thread-safety bugs
  are covered by the concurrency fix tests (interleaved lock acquisition), not by
  running the actual loop.
- **[Tests couple to internal call order]** → Accepted for `_finish_crew_setup`
  (ordering IS the contract). For `_reconcile_registry` and `_idle_monitor`, tests
  assert observable state (registry JSON, container stop calls) rather than
  internal call order.
- **[Three production fixes in a "test-only" change]** → The proposal says
  "no changes to server.py" but the concurrency bugs identified during analysis
  require minimal fixes (total ~15 lines) to make tests pass correctly. The
  alternative — writing tests that codify broken behavior — is worse.

## Migration Plan

No migration needed. This is a test + minimal-fix change:
1. Add test classes to `transport/test_transport.py`
2. Apply three minimal concurrency fixes to `transport/server.py`
3. Run `python -m pytest transport/test_transport.py` — all green
4. No deployment impact; no config changes
