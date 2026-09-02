# crew-lifecycle Specification (delta)

## MODIFIED Requirements

### Modified Requirement: Crew launch optionally allocates a UI port

`launch` gains a `dashboard` parameter (default `false`). When `dashboard=true` and `GA_UI_PORT_ENABLED=true`, `launch` allocates a port from the configured range, starts a transport-side listener, injects the session cookie and CORS origins, stores `ui_port` in the registry, and returns `ui_url` in the response. When `dashboard=false` (default), no port is allocated and `ui_url` is `null`.

### Modified Requirement: Crew nuke stops the UI listener

When `GA_UI_PORT_ENABLED=true` and the crew has a `ui_port` assigned, `nuke` SHALL stop the listener and release the port before removing the registry entry.

### New Requirement: REST API to retrofit or remove a dashboard

`POST /crews/{crew_id}/dashboard` SHALL allocate a UI port and start a listener for an already-running crew (same behaviour as `launch(dashboard=True)`). Returns `{"ui_url": "..."}` on success or an error if no ports are available or the crew already has a dashboard.

`DELETE /crews/{crew_id}/dashboard` SHALL stop the listener and release the port for a running crew. Returns `{"ui_url": null}` on success.

Both endpoints respect `GA_API_KEY` auth and `GA_UI_PORT_ENABLED`.

#### Scenario: POST /dashboard on a running crew
- **WHEN** `POST /crews/my-crew/dashboard` is called for a crew without a `ui_port`
- **THEN** a port is allocated, a listener is started, and the response includes `ui_url`

#### Scenario: DELETE /dashboard on a running crew
- **WHEN** `DELETE /crews/my-crew/dashboard` is called
- **THEN** the listener is stopped, the port released, and `ui_url` becomes null

#### Scenario: DELETE /dashboard when no dashboard is active
- **WHEN** `DELETE /crews/my-crew/dashboard` is called and the crew has no `ui_port`
- **THEN** the response returns `{"ui_url": null}` as a no-op — no error

#### Scenario: POST /dashboard when already active
- **WHEN** `POST /crews/my-crew/dashboard` is called and the crew already has a `ui_port`
- **THEN** the existing `ui_url` is returned with no change
