# transport/internal-fleet-api Specification

## Purpose

Portside-internal fleet data endpoint (`GET /internal/crews`) that serves
`ga-radar` a registry-sourced fleet snapshot for 5-second polling — no gateway
calls into crew containers, no bearer auth required.

## Requirements

### Requirement: `GET /internal/crews` is registry-reads-only

The `GET /internal/crews` handler SHALL build its response from the crew
registry only. It SHALL NOT call any crew gateway (`/api/spawn`,
`/api/crons`, or any per-crew path) to populate the response. The `agents`
array SHALL always be `[]` in the internal endpoint response. This invariant
must hold regardless of whether crew containers are running or stopped.

#### Scenario: No gateway calls on internal fleet request

- **WHEN** `GET /internal/crews` is requested while one or more crew containers are running
- **THEN** the transport returns a fleet payload sourced from the registry
- **THEN** no HTTP request is made to any crew container gateway

#### Scenario: agents array is always empty

- **WHEN** `GET /internal/crews` is requested for a crew that has active agent tasks
- **THEN** the response includes `"agents": []` for that crew
- **THEN** the public `GET /api/crews` response for the same crew still includes the live `agents` list

### Requirement: `captain.last_checkin_at` included in internal fleet payload

The `captain` object returned by `GET /internal/crews` SHALL include a
`last_checkin_at` field containing the ISO 8601 timestamp of the most recent
completed Captain check-in, as recorded in the crew registry. The field SHALL
be `null` when no check-in has been recorded yet.

#### Scenario: Captain with completed check-in

- **WHEN** a crew has a captain schedule entry with a recorded `last_checkin_at`
- **THEN** `GET /internal/crews` returns `captain.last_checkin_at` as an ISO 8601 string
- **THEN** the value matches the timestamp written by the most recent captain check-in

#### Scenario: Captain with no completed check-in

- **WHEN** a crew has a captain schedule entry but no check-in has completed yet
- **THEN** `GET /internal/crews` returns `captain.last_checkin_at: null`

#### Scenario: No captain schedule

- **WHEN** a crew has no captain schedule entry
- **THEN** `GET /internal/crews` returns `captain: null` for that crew

### Requirement: Internal fleet endpoint auth is transport-secret-only

`GET /internal/crews` SHALL require a valid `X-Transport-Token` header
(validated by `TransportSecretMiddleware`). It SHALL NOT require a bearer
API key. Requests without a valid `X-Transport-Token` SHALL receive HTTP 401.

#### Scenario: Valid transport token accepted

- **WHEN** `GET /internal/crews` is requested with a valid `X-Transport-Token`
- **THEN** the transport returns HTTP 200 with the fleet payload

#### Scenario: Missing transport token rejected

- **WHEN** `GET /internal/crews` is requested without `X-Transport-Token`
- **THEN** the transport returns HTTP 401
