## MODIFIED Requirements

### Requirement: RAVEN_SELF_CANCEL uses transport endpoint, not KiroCrew CLI

The `{{RAVEN_SELF_CANCEL}}` placeholder SHALL resolve to an instruction that calls
`POST /crews/{crew_id}/captain/stop` on the transport REST API via curl, authenticated
with the dashboard session cookie. It SHALL NOT instruct Raven to use `kirocrew cron
pause` — the captain schedule is registered in the transport's schedule registry and is
not visible inside the crew container via `kirocrew cron list`.

The transport SHALL expose `POST /crews/{crew_id}/captain/stop` as a crew-internal
endpoint that stops the captain schedule entry for the named crew. The request SHALL be
authenticated via the dashboard session cookie (`Cookie: mc_token_{port}=<value>`),
the same credential path used for spawn calls from inside the crew. The endpoint SHALL:

1. Look up the captain schedule entry in the transport registry for `crew_id`.
2. Disable it (set `enabled: false`) — the same operation as `captain(action="stop")`.
3. Return `{"status": "stopped"}` on success.
4. Return `404` with a JSON error body if no captain entry exists for this crew.
5. Return `400` if the entry exists but is already stopped.

The endpoint SHALL be reachable from inside the crew container at
`http://localhost:{transport_port}/crews/{crew_id}/captain/stop`, where
`{transport_port}` is the transport's port as exposed inside the container (64057).
The crew_id is available to the agent as `$KIROCREW_CREW_ID`.

#### Scenario: Raven self-cancels via transport endpoint on SDD completion
- **WHEN** Raven determines the standing orders are met and calls
  `POST /crews/{crew_id}/captain/stop` with the dashboard cookie
- **THEN** the transport disables the captain schedule entry for that crew
- **AND** returns `{"status": "stopped"}`
- **AND** subsequent captain monitor ticks do not fire a new Raven check-in

#### Scenario: Endpoint returns 404 when no captain entry exists
- **WHEN** `POST /crews/{crew_id}/captain/stop` is called for a crew with no captain entry
- **THEN** the transport returns HTTP 404 with a JSON error body

#### Scenario: Endpoint returns 400 when captain is already stopped
- **WHEN** `POST /crews/{crew_id}/captain/stop` is called and the captain entry is
  already disabled
- **THEN** the transport returns HTTP 400 indicating the captain is already stopped

#### Scenario: Endpoint requires dashboard cookie auth
- **WHEN** `POST /crews/{crew_id}/captain/stop` is called without a valid dashboard cookie
- **THEN** the transport returns HTTP 401 or HTTP 403
