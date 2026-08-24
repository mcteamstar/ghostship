# transport-test-coverage Specification

## Purpose
Ensures comprehensive test coverage for the transport layer's critical lifecycle
paths — startup reconciliation, idle monitoring, crew setup sequencing, and login
flow edge cases — plus concurrency fixes discovered during test authoring.
## Requirements
### Requirement: _reconcile_registry test coverage

The test suite SHALL exercise every branch of `_reconcile_registry` using a mock
`PodmanClient`, verifying observable side effects on the registry JSON file.

#### Scenario: Orphaned login container is swept
- **WHEN** `_reconcile_registry` runs AND a container named `ga-login-*` exists
- **THEN** the container is removed (via `_nuke_login_container`) and does not appear in the registry

#### Scenario: Gone crew is removed from registry
- **WHEN** `_reconcile_registry` runs AND a registered crew's container no longer exists (podman reports not found)
- **THEN** that crew entry is removed from the registry

#### Scenario: Stopped crew is restarted and cookie refreshed
- **WHEN** `_reconcile_registry` runs AND a registered crew's container exists but is stopped AND the gateway becomes ready within 30s
- **THEN** the container is started, a new cookie is minted, and the registry entry is updated with status "running" and the new cookie

#### Scenario: Stopped crew gateway fails to start
- **WHEN** `_reconcile_registry` runs AND a stopped crew's container is started but the gateway does not become ready within 30s
- **THEN** the registry entry is updated with status "stopped" (not removed)

#### Scenario: Running crew is left alone
- **WHEN** `_reconcile_registry` runs AND a registered crew's container is running
- **THEN** no action is taken on that crew entry

#### Scenario: Stale launching placeholder is cleaned up
- **WHEN** `_reconcile_registry` runs AND a registry entry has status "launching" but the container does not exist
- **THEN** that entry is removed from the registry

### Requirement: _idle_monitor test coverage

The test suite SHALL exercise `_idle_monitor`'s stop/skip logic for one
iteration cycle, using mocked HTTP responses for `/api/spawn` and `/api/crons`.

#### Scenario: Crew with active dispatch task is not stopped
- **WHEN** the idle monitor checks a crew AND `/api/spawn` returns an agent with `done: false`
- **THEN** the crew's `last_used` is updated and the container is NOT stopped

#### Scenario: Crew with enabled cron job is not stopped
- **WHEN** the idle monitor checks a crew AND `/api/crons` reports an enabled job
- **THEN** the crew's `last_used` is updated and the container is NOT stopped

#### Scenario: Genuinely idle crew is stopped
- **WHEN** the idle monitor checks a crew AND `last_used` exceeds `GA_IDLE_TIMEOUT_SECS` AND no active tasks or cron jobs exist
- **THEN** the container is stopped and registry status is set to "stopped"

#### Scenario: Recently used crew is not stopped
- **WHEN** the idle monitor checks a crew AND `last_used` is within `GA_IDLE_TIMEOUT_SECS`
- **THEN** no action is taken

#### Scenario: Already stopped crew is skipped
- **WHEN** the idle monitor checks a crew whose container is not running
- **THEN** no stop attempt is made

#### Scenario: 401 from crew gateway triggers cookie refresh attempt
- **WHEN** the idle monitor's HTTP call to `/api/spawn` or `/api/crons` returns 401
- **THEN** the system SHALL attempt a cookie refresh for that crew before deciding to stop it, rather than falling through to the stop path

### Requirement: _finish_crew_setup ordering test

The test suite SHALL verify that `_finish_crew_setup` executes its setup steps
in the correct sequence by recording call order.

#### Scenario: Setup steps execute in required order
- **WHEN** `_finish_crew_setup` is called with valid inputs
- **THEN** steps execute in this order: gateway wait → auth inject → config patch → restart → agent copy → skill copy → steering copy → OpenSpec seed → agent file wait → model patch → cookie mint → registry write

#### Scenario: Early failure aborts remaining steps
- **WHEN** `_finish_crew_setup` is called AND the gateway does not become ready after auth restart
- **THEN** cleanup is performed and an error dict is returned without executing later steps (no agent copy, no cookie mint)

### Requirement: Login flow edge case tests

The test suite SHALL exercise untested paths in the PTY-based login flow.

#### Scenario: URL not found within timeout
- **WHEN** `_handle_login_post` starts a PTY exec AND no device URL appears within 15 seconds
- **THEN** the login container is cleaned up and a 500 response is returned

#### Scenario: Region prompt answered
- **WHEN** `_handle_login_post` encounters a "Region" prompt in PTY output after answering the Start URL prompt
- **THEN** the configured `KIRO_REGION` value is written to the PTY stdin

#### Scenario: Concurrent POST /login rejection
- **WHEN** a `POST /login` arrives while `_login_pending` is not None
- **THEN** a 409 response is returned with message "Login already in progress"

#### Scenario: _handle_login_get clears pending guard on completion
- **WHEN** `_handle_login_get` detects auth completion
- **THEN** `_login_pending` is set to None under the lock AFTER the login container is nuked

### Requirement: _handle_login_get clears guard correctly under concurrency

The `_handle_login_get` handler SHALL clear `_login_pending` only after all
cleanup work (auth write, crew injection, container nuke) is complete, to
prevent a concurrent `POST /login` from starting a new flow while cleanup
artifacts (the login container) still exist.

#### Scenario: Guard cleared after container nuke
- **WHEN** `_handle_login_get` completes the auth flow
- **THEN** `_login_pending` is set to None strictly AFTER `_nuke_login_container` returns

#### Scenario: Concurrent POST during cleanup window
- **WHEN** a `POST /login` arrives while `_handle_login_get` is between auth detection and guard clear
- **THEN** the POST receives 409 (the guard is still set)

### Requirement: _reconcile_registry handles stale snapshot

When `_reconcile_registry` reads the registry snapshot and then releases the
lock for the per-crew restart loop, the registry state may have changed by the
time it writes back. The write-back SHALL re-read the registry under the lock
and merge only changes for crews that still exist in the current registry,
to avoid resurrecting entries that were removed concurrently.

#### Scenario: Crew removed between snapshot and write-back
- **WHEN** `_reconcile_registry` snapshots crew X, releases the lock, and another thread removes crew X before the write-back lock is acquired
- **THEN** the write-back does NOT re-add crew X to the registry

### Requirement: Test suite runs safely inside crew containers

The test suite SHALL be partitioned into Podman-dependent tests and pure unit
tests. Tests that require a real Podman socket SHALL be decorated with
`@unittest.skipUnless(shutil.which("podman"), "requires podman")` so they are
skipped automatically when Podman is not available (e.g., inside a crew
container). The top of the relocated test module (formerly
`transport/test_transport.py`, now living under `tests/` per the
`test-orchestration` capability) SHALL continue to document which test
classes are Podman-dependent and which are safe to run anywhere, and its
dual import-resolution shim (package-style `transport.server` import vs. a
flat-import fallback) SHALL be reconciled against the new location rather
than left to depend on which of the two branches happens to still resolve.

#### Scenario: Full suite completes inside a crew container
- **WHEN** the relocated test suite's unit-category tests are run inside a crew container where Podman is absent
- **THEN** Podman-dependent tests are skipped, all other tests run and pass, and the suite exits 0

#### Scenario: Full suite runs all tests on a host with Podman
- **WHEN** the relocated test suite's unit and integration categories are run on a host where Podman is available
- **THEN** all tests including Podman-dependent ones are executed

#### Scenario: Server module still importable after relocation
- **WHEN** the relocated test suite imports the transport server module
- **THEN** exactly one of the two existing import strategies (package-style `transport.server`, or the flat fallback) resolves correctly and deterministically from the new location — not by accident of which directory happens to be on `sys.path` for a given invocation

### Requirement: _idle_monitor handles 401 with cookie refresh

When the idle monitor's HTTP call to a crew's gateway returns HTTP 401, the
system SHALL attempt a cookie refresh (mint a new cookie via `_mint_cookie`)
before deciding whether the crew should be stopped. If the refresh succeeds,
the monitor SHALL retry the activity check. If the refresh fails, the monitor
SHALL skip that crew for the current cycle (fail-open) rather than stopping a
potentially active crew whose cookie merely expired.

#### Scenario: 401 triggers cookie refresh and retry
- **WHEN** `/api/spawn` returns 401 AND cookie refresh succeeds
- **THEN** the activity check is retried with the new cookie

#### Scenario: 401 with failed refresh skips crew
- **WHEN** `/api/spawn` returns 401 AND cookie refresh fails
- **THEN** the crew is NOT stopped for this cycle

