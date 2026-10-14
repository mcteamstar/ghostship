## ADDED Requirements

### Requirement: Crew container environment includes KIROCREW_CREW_ID

The crew container environment MUST include `KIROCREW_CREW_ID` set to the
crew's identifier (the registry key and the suffix of the container name
`gs-<crew_id>`).

Rationale: crew-internal scripts — including the Raven self-cancel mechanism
(`_RAVEN_SELF_CANCEL` in `transport/captain.py`) — use `$KIROCREW_CREW_ID` to
construct transport URLs of the form
`http://ga-transport:64057/crews/${crew_id}/captain/stop`. Without this var,
the path segment is empty and the request returns 401 before reaching the
endpoint's auth layer.

`KIROCREW_CREW_ID` MUST be set in the same `container_env` dict as
`KIROCREW_CORS_ORIGINS` in the `launch` code path (`transport/server.py`).

#### Scenario: Crew container receives KIROCREW_CREW_ID

- **WHEN** a crew is launched with crew_id "test-crew"
- **THEN** KIROCREW_CREW_ID is set to "test-crew" in the container environment

#### Scenario: Raven self-cancel constructs correct URL

- **GIVEN** KIROCREW_CREW_ID is set to "test-crew" in the container env
- **WHEN** Raven executes the self-cancel script
- **THEN** the curl URL is `http://ga-transport:64057/crews/test-crew/captain/stop`
- **AND** the request reaches the captain/stop endpoint handler
