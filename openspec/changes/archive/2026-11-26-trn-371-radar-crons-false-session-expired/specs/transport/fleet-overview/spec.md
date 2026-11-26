# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: Per-crew detail fetched from the crew API proxy`
- TO: `### Requirement: Per-crew detail fetched from Radar's per-crew endpoints`

## MODIFIED Requirements

### Requirement: Per-crew detail fetched from Radar's per-crew endpoints

The SPA SHALL show a running crew's active tasks from its live agents request, `GET /api/crews/{crew_id}/agents`, and a stopped crew's active tasks from the crew's fleet-payload `agents` array, with no live request for a stopped crew. It SHALL render captain state from the `captain` field in the fleet payload. It SHALL NOT request scheduled jobs for any crew, and SHALL NOT request `/crews/{crew_id}/api/crons`. For stopped crews, it SHALL show registry task and captain state and explain that live schedule data is unavailable. Per-crew detail requests SHALL use Radar's same-origin `/api/crews/{crew_id}/` endpoints, which the portal routes to Radar.

#### Scenario: Expanding a crew row shows agent and captain state
- **WHEN** the operator expands a crew row in the Radar UI
- **THEN** the SPA renders a running crew's active tasks from `GET /api/crews/{crew_id}/agents`, or a stopped crew's active tasks from the fleet payload agents array
- **THEN** captain state (enabled/paused, schedule, current task) is rendered from the `captain` field in the fleet payload
- **THEN** no request is sent to `/crews/{crew_id}/api/crons` and no scheduled jobs are appended

#### Scenario: Stopped crew detail shows appropriate message
- **WHEN** the operator expands a stopped crew row
- **THEN** task and captain state from the registry are shown (no gateway probe)
- **THEN** a message indicates live schedule data is unavailable
