## MODIFIED Requirements

### Crew container environment

REQ-ENV-1: The crew container environment MUST include `KIROCREW_CREW_ID` set
to the crew's identifier (the value used as the registry key and in the
container name `gs-<crew_id>`).

Rationale: crew-internal scripts — including the Raven self-cancel mechanism
(`_RAVEN_SELF_CANCEL` in `transport/captain.py`) — use `$KIROCREW_CREW_ID` to
construct transport URLs of the form
`http://ga-transport:64057/crews/${crew_id}/captain/stop`. Without this var,
the path segment is empty and the request fails before reaching the endpoint.

REQ-ENV-2: `KIROCREW_CREW_ID` MUST be set in the same `container_env` dict
as `KIROCREW_CORS_ORIGINS` in the `launch` code path (`transport/server.py`).
