# transport/dashboard-provisioning Specification

## Purpose

Defines Transport's dashboard provisioning operations for existing crews.

## Requirements

### Requirement: REST API to retrofit or remove a dashboard

`POST /crews/{crew_id}/dashboard` SHALL allocate a UI port and register it with Portal, idempotently reusing an active dashboard. `DELETE` SHALL remove the Portal registration, release the port, and return null, including when already inactive. Both endpoints SHALL honor `GA_API_KEY` authentication.

#### Scenario: POST /dashboard on a running crew
- **WHEN** `POST /crews/my-crew/dashboard` is called for a crew without a `dashboard_port`
- **THEN** a port is allocated, a listener is started, and the response includes `dashboard_url`

#### Scenario: DELETE /dashboard on a running crew
- **WHEN** `DELETE /crews/my-crew/dashboard` is called
- **THEN** the listener is stopped, the port released, and `dashboard_url` becomes null

#### Scenario: DELETE /dashboard when no dashboard is active
- **WHEN** `DELETE /crews/my-crew/dashboard` is called and the crew has no `dashboard_port`
- **THEN** the response returns `{"dashboard_url": null}` as a no-op — no error

#### Scenario: POST /dashboard when already active
- **WHEN** `POST /crews/my-crew/dashboard` is called and the crew already has a `dashboard_port`
- **THEN** the existing `dashboard_url` is returned with no change
