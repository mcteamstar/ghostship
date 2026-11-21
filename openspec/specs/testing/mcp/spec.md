# testing/mcp Specification

## Purpose

Defines verification coverage for MCP tool contracts and resource discovery.

## Requirements

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

### Requirement: Comp discovery resource aliases have test coverage
The test suite SHALL verify that both discovery URIs are registered, readable, and return identical comp listings.

#### Scenario: Canonical comps resource is discoverable
- **WHEN** resource discovery is requested
- **THEN** the test verifies `transport://comps` is listed and returns available comps

#### Scenario: Legacy compositions resource remains discoverable
- **WHEN** resource discovery is requested during the rollback window
- **THEN** the test verifies `transport://compositions` is listed and returns content identical to `transport://comps`
