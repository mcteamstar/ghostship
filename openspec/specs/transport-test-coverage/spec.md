# transport-test-coverage Specification

## Purpose
Ensures comprehensive test coverage for the transport layer's critical lifecycle
paths — startup reconciliation, idle monitoring, crew setup sequencing, and login
flow edge cases — plus concurrency fixes discovered during test authoring.

## Requirements

### Requirement: _cron_activity_since helper test coverage

The test suite SHALL exercise every branch of `_cron_activity_since` as a
pure-function unit test with no I/O.

#### Scenario: Running cron job reports activity

- **WHEN** `_cron_activity_since` is called with a payload containing a job where `is_running` is `True`
- **THEN** the function SHALL return `True`

#### Scenario: Recently completed cron job reports activity

- **WHEN** `_cron_activity_since` is called with a payload containing a job whose `running_since` or `last_run_ts` timestamp is greater than `last_used`
- **THEN** the function SHALL return `True`

#### Scenario: Stale cron job does not report activity

- **WHEN** `_cron_activity_since` is called with a payload containing a job whose timestamps are all less than or equal to `last_used` and `is_running` is `False`
- **THEN** the function SHALL return `False`

#### Scenario: Empty payload does not report activity

- **WHEN** `_cron_activity_since` is called with an empty dict or an empty jobs list
- **THEN** the function SHALL return `False`

#### Scenario: Non-dict payload does not report activity

- **WHEN** `_cron_activity_since` is called with a non-dict value (e.g. `None`, a list, a string)
- **THEN** the function SHALL return `False`

### Requirement: _cron_has_enabled_job helper test coverage

The test suite SHALL exercise every branch of `_cron_has_enabled_job` as a
pure-function unit test with no I/O.

#### Scenario: Payload with enabled job returns True

- **WHEN** `_cron_has_enabled_job` is called with a payload containing at least one job where `enabled` is `True`
- **THEN** the function SHALL return `True`

#### Scenario: Payload with only disabled jobs returns False

- **WHEN** `_cron_has_enabled_job` is called with a payload where all jobs have `enabled` set to `False` or absent
- **THEN** the function SHALL return `False`

#### Scenario: Empty jobs list returns False

- **WHEN** `_cron_has_enabled_job` is called with a payload whose `jobs` list is empty
- **THEN** the function SHALL return `False`

#### Scenario: Non-dict payload returns False

- **WHEN** `_cron_has_enabled_job` is called with a non-dict value
- **THEN** the function SHALL return `False`

### Requirement: _note_idle_skip helper test coverage

The test suite SHALL exercise `_note_idle_skip` reason-change deduplication.

#### Scenario: First call for a crew logs the reason

- **WHEN** `_note_idle_skip` is called for a crew with no prior entry in `_idle_skip_reasons`
- **THEN** the reason SHALL be logged at INFO level

#### Scenario: Same reason on second call is not re-logged

- **WHEN** `_note_idle_skip` is called twice for the same crew with the same reason
- **THEN** the log SHALL only be emitted once (on the first call)

#### Scenario: Different reason on second call IS logged

- **WHEN** `_note_idle_skip` is called for a crew and then called again with a different reason
- **THEN** the second log SHALL be emitted

### Requirement: _schedule_monitor test coverage

The test suite SHALL exercise `_schedule_monitor` single-iteration logic using
mock registry state and mock `_ensure_crew_running` / `_crew_api` /
`_crew_api_with_recovery` callables. No daemon thread is started in tests.

#### Scenario: Due job fires against crew gateway

- **WHEN** the schedule monitor finds a job whose `next_fire_at` has passed AND `_ensure_crew_running` succeeds AND the gateway reports the job enabled
- **THEN** `_crew_api_with_recovery` SHALL be called with `POST /api/spawn` and `next_fire_at` SHALL be advanced

#### Scenario: Not-yet-due job is skipped

- **WHEN** the schedule monitor finds a job whose `next_fire_at` is in the future
- **THEN** `_crew_api_with_recovery` SHALL NOT be called for that job

#### Scenario: Disabled job is skipped

- **WHEN** the schedule monitor finds a job where `enabled` is `False`
- **THEN** `_crew_api_with_recovery` SHALL NOT be called for that job

#### Scenario: Captain-type job is skipped

- **WHEN** the schedule monitor finds a job with `type == "captain"`
- **THEN** `_crew_api_with_recovery` SHALL NOT be called for that job

#### Scenario: _ensure_crew_running failure advances next_fire_at without firing

- **WHEN** `_ensure_crew_running` raises an exception for a due job
- **THEN** `next_fire_at` SHALL still be advanced in the registry AND `_crew_api_with_recovery` SHALL NOT be called

#### Scenario: Gateway disables job — registry synced and job not fired

- **WHEN** the gateway GET /api/crons response shows a job with `enabled: false`
- **THEN** the registry schedule entry SHALL have `enabled` set to `False` AND `_crew_api_with_recovery` SHALL NOT fire for that job

#### Scenario: One-shot job is disabled and deleted from gateway after fire

- **WHEN** a due job has `one_shot: True` and fires successfully
- **THEN** the registry schedule entry SHALL have `enabled` set to `False` AND `_crew_api_with_recovery` SHALL be called with `DELETE /api/crons/<job_id>`

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

The test suite SHALL exercise `_idle_monitor` single-iteration logic using
`FakePodmanClient` for container checks and mock HTTP responses for
`/api/spawn` and `/api/crons`. No daemon thread is started in tests.

#### Scenario: Crew with active task is not stopped

- **WHEN** the idle monitor checks a crew AND `/api/spawn` returns at least one agent with `done: false`
- **THEN** `container_stop` SHALL NOT be called AND `last_used` SHALL be updated via `_touch_crew`

#### Scenario: Crew with enabled cron job is not stopped

- **WHEN** the idle monitor checks a crew AND `/api/crons` reports an enabled job
- **THEN** `container_stop` SHALL NOT be called

#### Scenario: Crew with recent cron activity is not stopped

- **WHEN** the idle monitor checks a crew AND `/api/crons` reports a job whose `last_run_ts` is more recent than `last_used`
- **THEN** `container_stop` SHALL NOT be called

#### Scenario: Genuinely idle crew is stopped

- **WHEN** the idle monitor checks a crew AND `last_used` exceeds `GA_IDLE_TIMEOUT_SECS` AND no active tasks or cron jobs exist
- **THEN** `container_stop` SHALL be called AND the registry entry status SHALL be set to `"stopped"`

#### Scenario: Already-stopped container is skipped

- **WHEN** the idle monitor checks a crew whose container is not running
- **THEN** `container_stop` SHALL NOT be called

#### Scenario: auth_required crew is skipped

- **WHEN** the idle monitor encounters a crew with `status == "auth_required"`
- **THEN** `container_stop` SHALL NOT be called for that crew

#### Scenario: Recently used crew within timeout is not stopped

- **WHEN** the idle monitor checks a crew AND `last_used` is within `GA_IDLE_TIMEOUT_SECS`
- **THEN** `container_stop` SHALL NOT be called

#### Scenario: 401 response triggers cookie refresh before stop decision

- **WHEN** the idle monitor's HTTP call to `/api/spawn` returns 401 and `_mint_cookie` returns a new cookie
- **THEN** the system SHALL retry with the refreshed cookie before deciding whether to stop the crew

#### Scenario: Cookie refresh failure causes fail-open skip

- **WHEN** the idle monitor receives 401 AND `_mint_cookie` returns `None`
- **THEN** `container_stop` SHALL NOT be called (fail-open) and the skip reason SHALL be recorded

#### Scenario: Captain schedule hold prevents stop

- **WHEN** the idle monitor detects an enabled captain-type schedule entry in the registry
- **THEN** `container_stop` SHALL NOT be called AND `_touch_crew` SHALL be called

#### Scenario: TOCTOU guard prevents stop when last_used advanced during checks

- **WHEN** `last_used` is updated (via `_touch_crew`) between the initial idle check and the registry lock acquisition
- **THEN** `container_stop` SHALL NOT be called

#### Scenario: _stopping flag prevents duplicate stop

- **WHEN** a crew's registry entry already has `_stopping: True` when the idle monitor acquires the registry lock
- **THEN** `container_stop` SHALL NOT be called a second time

#### Scenario: _stopping flag is cleared after stop completes

- **WHEN** `container_stop` succeeds
- **THEN** the registry entry SHALL have `_stopping` removed AND `status` set to `"stopped"`

#### Scenario: container_stop failure clears _stopping flag but does not update status

- **WHEN** `container_stop` raises an exception
- **THEN** the `_stopping` flag SHALL be cleared AND the registry `status` SHALL NOT be changed to `"stopped"`

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

### Requirement: e2e suite fixture model

The e2e test suite SHALL use a module-level shared crew as the primary fixture,
launched once per test file rather than once per test class, so that stateless
test classes share a single running crew without incurring per-class launch and
teardown overhead.

Each test file SHALL declare a module-level `SHARED_CREW_ID` constant and
implement `setUpModule` / `tearDownModule` to launch and nuke the shared crew.
Test classes that operate only on task, job, supply, or schema namespaces (with
no cross-class state interference) SHALL read `CREW_ID` from the module-level
`SHARED_CREW_ID` and SHALL NOT implement their own `setUpClass` or
`tearDownClass` that launch or nuke a crew.

#### Scenario: Module-level crew is launched once per file
- **WHEN** the e2e test runner imports a test file
- **THEN** exactly one `setUpModule` launch call is made for that file, shared by all stateless test classes within it

#### Scenario: Module-level crew is torn down after all tests in the file complete
- **WHEN** all tests in a test file have run
- **THEN** `tearDownModule` nukes the shared crew exactly once

#### Scenario: Stateless test classes use the shared crew
- **WHEN** `TestDispatchPickup`, `TestSupplyEvac`, `TestScheduleTool`, `TestResponseSchemas`, or the stateless `TestErrorPaths` tests run
- **THEN** they operate against the module-level shared crew and do not launch or nuke any crew of their own

#### Scenario: TestSteerTool uses its own crew
- **WHEN** `TestSteerTool.setUpClass` runs
- **THEN** a dedicated crew named `e2e-steer` is launched; `tearDownClass` nukes it

#### Scenario: TestCrewLifecycle uses its own crew
- **WHEN** `TestCrewLifecycle.test_launch_and_nuke` runs
- **THEN** it launches and nukes a dedicated `e2e-lifecycle` crew independently of the shared crew

#### Scenario: TestCaptainStatusStoppedCrew uses its own crew
- **WHEN** `TestCaptainStatusStoppedCrew.setUpClass` runs
- **THEN** a dedicated crew is launched and stopped via Podman; `tearDownClass` nukes it

#### Scenario: TestErrorPaths lifecycle tests use throw-away crews
- **WHEN** `test_pickup_nonexistent_task`, `test_launch_duplicate_crew`, or `test_nuke_without_confirm` runs
- **THEN** each test launches and nukes its own short-lived throw-away crew within the test method body, using a distinct `crew_id` that does not collide with `SHARED_CREW_ID`

### Requirement: _crew_api_with_recovery test coverage

The test suite SHALL exercise `_crew_api_with_recovery` and its three phase helpers using mocked HTTP responses, verifying retry behaviour and error propagation.

#### Scenario: Phase 0 — transient 503 is retried
- **WHEN** `_crew_api_with_recovery` receives a 503 from the first call
- **THEN** `_phase0_transient_503` retries the call and returns the second response

#### Scenario: Phase 1 — stale cookie triggers refresh
- **WHEN** `_crew_api_with_recovery` receives a 401 indicating a stale cookie
- **THEN** `_phase1_stale_cookie` refreshes the cookie and retries the call

#### Scenario: Phase 2 — dead gateway triggers container restart
- **WHEN** `_crew_api_with_recovery` cannot reach the crew gateway
- **THEN** `_phase2_dead_gateway` restarts the container, waits for readiness, and retries

#### Scenario: _ensure_crew_running leader failure propagates to waiters
- **WHEN** the leader coroutine in `_ensure_crew_running` raises during restart
- **THEN** waiters that were blocked on the same Event receive the same exception rather than proceeding with stale registry status

### Requirement: _ssl_context_factory test coverage

The test suite SHALL exercise `_ssl_context_factory` (the direct-TLS path via `GA_TLS_CERTFILE`/`GA_TLS_KEYFILE`) to verify TLS version floor and file-path gating.

#### Scenario: TLS disabled — no cert/key configured
- **WHEN** `GA_TLS_CERTFILE` and `GA_TLS_KEYFILE` are not set
- **THEN** no `_ssl_context_factory` is registered on the uvicorn kwargs

#### Scenario: TLS enabled — valid cert and key files
- **WHEN** `GA_TLS_CERTFILE` and `GA_TLS_KEYFILE` are both set to readable files
- **THEN** `_ssl_context_factory` is registered and the returned context enforces TLS 1.2 as minimum

#### Scenario: TLS enabled — missing cert file raises
- **WHEN** `GA_TLS_CERTFILE` points to a non-existent file
- **THEN** `_ssl_context_factory` raises an appropriate error at startup

### Requirement: TransportSecretMiddleware and _load_transport_secret test coverage

The test suite SHALL exercise `TransportSecretMiddleware` and `_load_transport_secret`, covering the configured and unconfigured paths.

#### Scenario: Secret not configured — requests pass through
- **WHEN** no transport secret is configured (`GA_TRANSPORT_SECRET` absent / empty)
- **THEN** all requests pass through `TransportSecretMiddleware` without a 401

#### Scenario: Secret configured — correct header passes
- **WHEN** a transport secret is configured AND a request carries the correct `X-Transport-Token` value
- **THEN** the request passes through

#### Scenario: Secret configured — wrong header returns 401
- **WHEN** a transport secret is configured AND a request carries an incorrect `X-Transport-Token`
- **THEN** `TransportSecretMiddleware` returns 401

#### Scenario: Secret configured — missing header returns 401
- **WHEN** a transport secret is configured AND a request has no `X-Transport-Token` header
- **THEN** `TransportSecretMiddleware` returns 401

#### Scenario: Constant-time comparison used
- **WHEN** `TransportSecretMiddleware` validates the token
- **THEN** `hmac.compare_digest` (or equivalent constant-time compare) is used, not `==`

### Requirement: Streaming transfer classes have test coverage

`_ResponseChunkReader` and `_TarMemberStream` in `transport/files.py` SHALL have unit tests covering: normal reads, cross-chunk-boundary reads, empty stream, missing tar member (raises ValueError), truncated/invalid archive (raises), close idempotency, and context manager protocol.

#### Scenario: ResponseChunkReader reads across chunk boundaries
- **WHEN** a `_ResponseChunkReader` is constructed from multiple small chunks
- **THEN** `read(n)` returns exactly n bytes assembled correctly across chunk boundaries

#### Scenario: TarMemberStream raises on missing member
- **WHEN** a `_TarMemberStream` is constructed with an `expected_path` that is not present in the archive
- **THEN** a `ValueError` is raised at construction time

#### Scenario: _transfer_upload slash-ref workaround is exercised
- **WHEN** `_transfer_upload` is called and `git rev-parse HEAD` fails (empty working tree after clone)
- **THEN** `git checkout -b <branch> origin/<branch>` is called to check out the first available remote branch

### Requirement: Static guardrail test prevents hardcoded pre-0.9.0 SEL path
The test suite SHALL include a static-assertion test that scans all Python files under `transport/` and fails if any file contains a string literal matching a pre-0.9.0 KiroCrew SEL key path pattern (`sel_key`, `sel-key`, `sel.key`, or `/sel/` as a path segment). This test SHALL pass on the current tree (no such literal exists today) and SHALL fail if such a literal is introduced in a future commit, preventing silent regression to the pre-0.9.0 path convention.

The test SHALL NOT flag:
- The SQL `SELECT` keyword (a false-positive on `sel`) in `transport/container_scripts/read_auth.py`.
- The `.local_secret` docstring in `transport/lifecycle.py` (unrelated internal-API-secret reference).
- The `policy_signing_key` / `trust_keys` strings in `transport/container_scripts/inject_policy.py` (ghostship's own policy key, not the SEL key).

#### Scenario: Test passes on clean tree
- **WHEN** the guardrail test is run against the transport source tree that contains no pre-0.9.0 SEL key path literal
- **THEN** the test passes with zero offenders reported

#### Scenario: Test fails when a pre-0.9.0 SEL literal is introduced
- **WHEN** any Python file under `transport/` is modified to include a string literal matching `sel_key`, `sel-key`, `sel.key`, or `/sel/` as a path segment
- **THEN** the guardrail test fails and identifies the offending file and line number

#### Scenario: SQL SELECT keyword is not a false positive
- **WHEN** the guardrail test runs and `transport/container_scripts/read_auth.py` contains `SELECT key, value FROM auth_kv`
- **THEN** the test passes; the SQL `SELECT` keyword does not match the SEL path pattern

#### Scenario: policy_signing_key and local_secret are not false positives
- **WHEN** the guardrail test runs and `transport/container_scripts/inject_policy.py` contains `policy_signing_key` and `trust_keys`, and `transport/lifecycle.py` contains `.local_secret`
- **THEN** the test passes; neither string matches the SEL path pattern

### Requirement: _captain_monitor test coverage

The test suite SHALL exercise `_captain_monitor` single-iteration logic using
mock registry state, mock `_ensure_crew_running`, and mock `_steer_captain_checkin`.
No daemon thread is started in tests.

#### Scenario: Due captain entry triggers steer/dispatch

- **WHEN** the captain monitor finds an enabled captain entry with `next_fire_at` in the past AND `_ensure_crew_running` succeeds
- **THEN** `_steer_captain_checkin` SHALL be called AND `next_fire_at` SHALL be advanced

#### Scenario: Not-yet-due captain entry is skipped

- **WHEN** the captain monitor finds a captain entry with `next_fire_at` in the future
- **THEN** `_steer_captain_checkin` SHALL NOT be called

#### Scenario: Disabled captain entry is skipped

- **WHEN** the captain monitor finds a captain entry with `enabled: False`
- **THEN** `_steer_captain_checkin` SHALL NOT be called

#### Scenario: Sentinel file presence auto-pauses captain schedule

- **WHEN** the captain monitor reads the workspace sentinel file AND it is present
- **THEN** the schedule entry `enabled` SHALL be set to `False` AND `_steer_captain_checkin` SHALL NOT be called

#### Scenario: _ensure_crew_running failure advances next_fire_at

- **WHEN** `_ensure_crew_running` raises for a due captain entry
- **THEN** `next_fire_at` SHALL be advanced AND `_steer_captain_checkin` SHALL NOT be called

### Requirement: _reseed_crew_schedules captain branch test coverage
The test suite SHALL exercise the three captain schedule type branches in `_reseed_crew_schedules`: no existing task → `_dispatch_captain_checkin` called; has living task → neither dispatch nor steer called; session gone (dead task) → `_dispatch_captain_checkin` called and `current_task_id` cleared.

#### Scenario: Captain schedule reseeds with no prior task
- **WHEN** `_reseed_crew_schedules` runs and the captain schedule has no `current_task_id`
- **THEN** `_dispatch_captain_checkin` is called to start a fresh check-in

### Requirement: _append_captain_mail I/O path test coverage
The test suite SHALL exercise `_append_captain_mail` with a mock `container_exec`, covering: signing secret present → signed mail written with valid `X-Admiral-Sig` header; no signing secret → unsigned mail written. Related mailbox read helpers (`_mail_count`, `_read_all_mail_counts`, `_skim_all_mailboxes`) SHALL be tested with mock tar archive responses.

#### Scenario: Captain mail is signed when signing secret is present
- **WHEN** `_append_captain_mail` is called with a crew that has a `signing_secret`
- **THEN** the written mail message contains a valid `X-Admiral-Sig` header

### Requirement: _captain_do_order/status/stop branch test coverage
The test suite SHALL cover the main execution branches in `_captain_do_order` (template resolution, mail delivery, registry write-back, active-task steer branch), `_captain_do_status` (enabled/disabled state, mailbox counts), and `_captain_do_stop` (schedule disable, registry update).

#### Scenario: do_order delivers mail and updates registry
- **WHEN** `_captain_do_order` is called with a valid standing order
- **THEN** `_append_captain_mail` is called and the registry schedule entry is updated with the new order

### Requirement: _handle_crew_ui_ws_proxy test coverage
The test suite SHALL exercise `_handle_crew_ui_ws_proxy` covering: upstream connection failure before client accept (returns 502); normal bidirectional relay (client→upstream and upstream→client message forwarding); cookie near-expiry refresh mid-session (refresh is called and connection continues); missing `websockets` dependency (returns 501 or logs appropriate error).

#### Scenario: WS proxy handles upstream failure before accept
- **WHEN** `_handle_crew_ui_ws_proxy` is called and the upstream WebSocket connection fails before the client connection is accepted
- **THEN** the handler returns a non-2xx HTTP response without crashing

#### Scenario: WS proxy relays messages bidirectionally
- **WHEN** `_handle_crew_ui_ws_proxy` establishes both connections successfully
- **THEN** messages sent from the client are forwarded to upstream, and messages from upstream are forwarded to the client

### Requirement: Claude login lifecycle test coverage
The test suite SHALL exercise the Claude OAuth login flow: `_start_claude_login_container` (container start, binary probe), `_initiate_claude_login` (PTY exec, URL extraction, timeout), and `_nuke_claude_login_container` (container cleanup). Tests SHALL mirror the structure of the existing Codex login tests (`test_trn172_codex_backend.py`). `container_exec_stdin` SHALL be mocked for PTY interaction.

#### Scenario: Claude login extracts URL from PTY output
- **WHEN** `_initiate_claude_login` runs and the PTY emits a login URL
- **THEN** the URL is extracted and returned as the login URL

#### Scenario: Claude login times out if no URL appears
- **WHEN** `_initiate_claude_login` runs and no URL appears within the timeout
- **THEN** the login container is nuked and a timeout error is returned

### Requirement: container_exec_stdin unit test coverage
The test suite SHALL include unit tests for `container_exec_stdin` using `socketpair()` to simulate the Unix socket connection, covering: HTTP 101 upgrade handshake; bidirectional relay (stdin→socket, socket→stdout); exit-code extraction from the trailer. Error-path tests SHALL cover `secret_create` / `secret_delete`, `network_disconnect` / `network_rm`, and `volume_create` / `volume_remove` Podman management methods.

#### Scenario: container_exec_stdin completes HTTP 101 upgrade
- **WHEN** `container_exec_stdin` is called with a mock socket that responds with HTTP 101
- **THEN** the upgrade handshake completes and the stdin content is forwarded to the socket

#### Scenario: container_exec_stdin extracts exit code from trailer
- **WHEN** the exec session ends and the socket sends a trailer with exit code
- **THEN** `container_exec_stdin` returns the correct exit code

### Requirement: lifecycle.py unit test module exists

The test suite SHALL include a dedicated `tests/unit/test_lifecycle.py` module covering `transport/lifecycle.py`. The module SHALL follow the same design principles as other unit modules in `tests/unit/`: dependency injection over module patching, no filesystem I/O, and `FakePodmanClient` for all container runtime calls.

#### Scenario: test_lifecycle.py is present and importable
- **WHEN** `pytest tests/unit/test_lifecycle.py` is executed in an environment with no Podman socket
- **THEN** all tests in the module are collected and run without import errors or skips due to missing Podman

#### Scenario: test_lifecycle.py runs within the existing unit suite
- **WHEN** `pytest tests/unit/` is executed
- **THEN** `test_lifecycle.py` tests are included in the run alongside `test_config.py`, `test_login.py`, `test_registry_lock.py`, and `test_sentinel.py`
### Requirement: CaddyPortal port pool allocation

The test suite SHALL exercise `CaddyPortal.allocate_port` and `release_port`,
confirming correct scan behaviour and the exhaustion guard.

#### Scenario: First available port is returned

- **WHEN** a `CaddyPortal` is constructed with a range of N ports and none are
  in use
- **THEN** `allocate_port()` returns the range start port and adds it to
  `_dashboard_ports_in_use`

#### Scenario: Already-in-use port is skipped

- **WHEN** the range-start port is already in `_dashboard_ports_in_use`
- **THEN** `allocate_port()` returns the next free port in the range

#### Scenario: Exhausted pool raises RuntimeError

- **WHEN** every port in the configured range is in `_dashboard_ports_in_use`
- **THEN** `allocate_port()` raises `RuntimeError`

#### Scenario: Released port becomes available for reallocation

- **WHEN** a port is released via `release_port()` and `allocate_port()` is
  called again
- **THEN** the released port is returned

#### Scenario: release_port is idempotent for absent port

- **WHEN** `release_port()` is called with a port not in `_dashboard_ports_in_use`
- **THEN** no exception is raised and `_dashboard_ports_in_use` is unchanged

### Requirement: Module-level port wrappers delegate to default portal

The thin-wrapper functions `_allocate_dashboard_port` and
`_release_dashboard_port` SHALL delegate to the module-default `CaddyPortal`
built from the current module globals.

#### Scenario: _allocate_dashboard_port allocates from module range

- **WHEN** `_allocate_dashboard_port()` is called with the module globals set to
  a known range
- **THEN** it returns a port within that range and `_dashboard_ports_in_use` is
  updated

#### Scenario: _release_dashboard_port removes the port

- **WHEN** `_release_dashboard_port(port)` is called with a previously allocated
  port
- **THEN** the port is removed from `_dashboard_ports_in_use`

### Requirement: CaddyPortal.register_crew builds correct reverse-proxy config

`CaddyPortal.register_crew` SHALL issue a `PUT` to the Caddy admin API with a
server object whose routes satisfy the documented routing contract.

#### Scenario: Happy-path PUT 200 registers crew

- **WHEN** `register_crew(crew_id, port)` is called and the mocked HTTP client
  returns 200
- **THEN** exactly one PUT request is made to
  `http://ga-portal:2019/config/apps/http/servers/crew-{crew_id}` with a valid
  server object, and no exception is raised

#### Scenario: PUT 201 is also treated as success

- **WHEN** the mocked client returns 201
- **THEN** no exception is raised and no retry is attempted

#### Scenario: PUT 409 (already exists) is treated as idempotent success

- **WHEN** the mocked client returns 409
- **THEN** no exception is raised and no retry is attempted

#### Scenario: Server object listen port matches argument

- **WHEN** `register_crew("abc", 8765)` is called
- **THEN** the PUT body contains `"listen": [":8765"]`

#### Scenario: Server object uses crew-scoped @id

- **WHEN** `register_crew("abc", 8765)` is called
- **THEN** the PUT body contains `"@id": "crew-abc"`

#### Scenario: Reverse proxy rewrite uses correct crew path prefix

- **WHEN** `register_crew("abc", 8765)` is called
- **THEN** the reverse proxy handler's `rewrite.uri` starts with
  `/crews/abc/ui`

#### Scenario: Transport-token header is injected in proxy handler

- **WHEN** `register_crew` generates the server object
- **THEN** the reverse proxy handler's `headers.request.set` contains
  `X-Transport-Token` set to `{file./run/secrets/ga-transport-secret}`

#### Scenario: WebSocket route appears before HTTP catch-all route

- **WHEN** `register_crew` generates the server object
- **THEN** `routes[0]` matches on `Connection: Upgrade` (the WebSocket route)
  and `routes[1]` is the HTTP catch-all, ensuring upgrades bypass forward-auth

#### Scenario: Forward-auth handler included when api_key is set

- **WHEN** `CaddyPortal` is constructed with a non-empty `api_key` and
  `register_crew` is called
- **THEN** the HTTP catch-all route's `handle` list contains a forward-auth
  handler targeting `/dashboard/auth` before the reverse-proxy handler

#### Scenario: Forward-auth handler absent when api_key is empty

- **WHEN** `CaddyPortal` is constructed with `api_key=""` and `register_crew`
  is called
- **THEN** the HTTP catch-all route's `handle` list contains only the
  reverse-proxy handler (no forward-auth handler)

#### Scenario: Transient failure retries and succeeds

- **WHEN** the mocked client returns 500 on the first attempt and 200 on the
  second
- **THEN** register_crew retries and returns without raising, and exactly two
  PUT requests are made

#### Scenario: All retries exhausted — no exception raised

- **WHEN** the mocked client returns 500 on all three attempts
- **THEN** `register_crew` returns without raising (it only logs a warning)

### Requirement: CaddyPortal.deregister_crew calls Caddy admin DELETE

`CaddyPortal.deregister_crew` SHALL call `DELETE` on the correct admin URL and
handle non-fatal response codes gracefully.

#### Scenario: DELETE 200 deregisters crew

- **WHEN** `deregister_crew("abc")` is called and the mocked client returns 200
- **THEN** the DELETE is made to `http://ga-portal:2019/id/crew-abc` and no
  exception is raised

#### Scenario: DELETE 204 is also treated as success

- **WHEN** the mocked client returns 204
- **THEN** no exception is raised

#### Scenario: DELETE 404 is handled gracefully

- **WHEN** the mocked client returns 404
- **THEN** no exception is raised (crew was already removed)

#### Scenario: DELETE non-2xx/404 logs warning but does not raise

- **WHEN** the mocked client returns 500
- **THEN** no exception is raised (nuke must not be blocked by Caddy errors)

#### Scenario: DELETE connection error logs warning but does not raise

- **WHEN** the HTTP call raises an exception
- **THEN** `deregister_crew` catches it and returns without re-raising

### Requirement: Module-level thin wrappers delegate to default portal

`_caddy_register_crew` and `_caddy_deregister_crew` SHALL delegate to
`_get_default_portal()` and produce the same observable HTTP calls as the
direct portal methods.

#### Scenario: _caddy_register_crew issues PUT to admin API

- **WHEN** `_caddy_register_crew("test", 9000)` is called with mocked httpx
- **THEN** a PUT request is made to the Caddy admin URL for `crew-test`

#### Scenario: _caddy_deregister_crew issues DELETE to admin API

- **WHEN** `_caddy_deregister_crew("test")` is called with mocked httpx
- **THEN** a DELETE request is made to the Caddy admin URL for `crew-test`

### Requirement: _caddy_admin_url returns correct constant

The `_caddy_admin_url` helper SHALL always return the fixed Caddy admin base
URL.

#### Scenario: Admin URL is the expected constant

- **WHEN** `_caddy_admin_url()` is called
- **THEN** it returns `"http://ga-portal:2019"`

### Requirement: CaddyPortal constructor stores fields correctly

`CaddyPortal.__init__` SHALL store all constructor arguments as instance
attributes accessible by the instance methods.

#### Scenario: Constructor fields are correctly stored

- **WHEN** a `CaddyPortal` is constructed with explicit `port`, `api_key`,
  `port_range_start`, and `port_range_size`
- **THEN** `portal._port`, `portal._api_key`, `portal._range_start`, and
  `portal._range_size` match the supplied values
