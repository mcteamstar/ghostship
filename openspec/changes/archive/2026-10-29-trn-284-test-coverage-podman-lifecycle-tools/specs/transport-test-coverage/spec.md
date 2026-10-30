## MODIFIED Requirements

### Requirement: PodmanClient has dedicated unit tests

`transport/podman.py` SHALL have a dedicated `tests/unit/test_podman.py` that
exercises PodmanClient against a mock or patched HTTP transport. Key paths covered
SHALL include container create/start/stop/inspect, `container_exec_stdin`, archive
put/get, network create/connect/disconnect, volume create/remove, and error handling
(HTTP 500, malformed JSON, socket failure).

`FakePodmanClient` in `conftest.py` SHALL be verified to implement the same interface
as the real `PodmanClient` (same method signatures and return shapes for all methods
it stubs).

#### Scenario: PodmanClient error paths produce structured exceptions
- **WHEN** the Podman socket returns HTTP 500 for a container operation
- **THEN** PodmanClient raises a typed exception (not a bare dict or silent None)

#### Scenario: FakePodmanClient matches real PodmanClient interface
- **WHEN** FakePodmanClient is instantiated in tests
- **THEN** it exposes the same public methods as PodmanClient with compatible signatures

### Requirement: lifecycle.py critical paths have unit test coverage

`transport/lifecycle.py` SHALL have unit test coverage for the following paths in
`tests/unit/test_lifecycle.py`:
- `_reconcile_registry` — stale entry removal, timestamp guard
- `_reseed_crew_schedules` — schedule restoration on registry reload
- `_dispatch_batch` / `_pickup_single` — error paths and partial batch handling
- `_mint_cookie` / `_refresh_cookie` — cookie issuance and atomic update
- `_prewarm_crew` — pre-warm success and failure paths

#### Scenario: _reconcile_registry removes stale entries
- **WHEN** `_reconcile_registry` runs and finds a crew with no container
- **THEN** the crew entry is removed from the registry

#### Scenario: _reseed_crew_schedules restores captain entries
- **WHEN** `_reseed_crew_schedules` runs after a transport restart
- **THEN** captain schedule entries present in the registry are re-registered with the gateway

### Requirement: tools.py MCP API surface has dedicated unit tests

`transport/tools.py` SHALL have a dedicated `tests/unit/test_tools.py` covering:
- `nuke()` with `confirm=True` and `confirm=False`
- `schedule()` validation: missing name, invalid interval, cancel non-existent job
- `dispatch()` error paths: crew not found, gateway unreachable
- `_schedule_cancel` success and not-found paths
- `resource_agents` and `resource_jobs` MCP resource handlers
- `supply` / `evac` / `pickup` branch coverage for stopped and running crews

#### Scenario: nuke() requires explicit confirmation
- **WHEN** `nuke(crew_id="x", confirm=False)` is called
- **THEN** no container operation is performed and a preview response is returned

#### Scenario: dispatch() returns structured error on crew-not-found
- **WHEN** `dispatch(crew_id="nonexistent", ...)` is called
- **THEN** the response contains an `error` field describing the failure

### Requirement: captain_engine.py dispatch and steer paths have unit tests

`tests/unit/test_captain_engine.py` SHALL cover:
- `_dispatch_captain_checkin` with memory pressure skip and model override
- `_steer_captain_checkin` with 400-continue branch and non-400 error
- `_captain_do_order` for interval vs cron schedule, and re-order of existing schedule
- `_record_memory_pressure_cycle` escalation at threshold boundary

#### Scenario: Memory pressure skips dispatch
- **WHEN** `_dispatch_captain_checkin` is called and host memory is below threshold
- **THEN** no spawn call is made and `immediate_dispatch_error` starts with `memory_pressure:`

### Requirement: server.py proxy handlers have basic unit tests

`tests/unit/test_server.py` SHALL include at minimum:
- UI proxy handler: cookie-refresh path when `gs_session` is missing
- Crew API proxy handler: 404 on unknown crew, correct upstream URL construction

### Requirement: files.py upload path has unit tests

`tests/unit/test_files.py` SHALL cover the upload path including:
- Path-traversal rejection in `_safe_workspace_path`
- Git-bundle clone fallback when the direct upload fails
- HMAC token expiry and mode-mismatch rejection

### Requirement: academy.py composition registry has error-path tests

`tests/unit/test_academy.py` SHALL cover:
- `_load_composition_registry` with missing file, malformed JSON, unknown composition
- `AcademyLoader._stage_mcp` with `${VAR}` substitution and missing variable
