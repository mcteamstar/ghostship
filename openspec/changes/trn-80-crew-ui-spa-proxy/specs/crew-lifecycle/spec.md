# crew-lifecycle Specification (delta)

## MODIFIED Requirements

### Modified Requirement: Crew launch allocates a UI port

When `GA_UI_PORT_ENABLED=true`, `launch` SHALL allocate a unique host port from the configured range and bind it to the crew container's internal gateway port. The allocated port SHALL be stored in the crew registry and returned in the launch response as `ui_url`. If all ports in the range are allocated, `launch` SHALL return an error.

### Modified Requirement: Crew nuke releases the UI port

When `GA_UI_PORT_ENABLED=true`, `nuke` SHALL release the crew's allocated UI port back to the pool.
