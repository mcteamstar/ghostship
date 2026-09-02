# trn-captain-mail Specification (delta)

## MODIFIED Requirements

### Modified Requirement: Captain status response

`captain(action="status")` SHALL include `last_checkin_at` (ISO 8601 UTC) — the wall-clock time the most recent Raven check-in fired for this crew. If no check-in has fired yet, `last_checkin_at` SHALL be `null`.

Subject listings in the captain status response SHALL use the structured `{"subject": ..., "received_at": ...}` format. See `mail-timestamps/spec.md`.

#### Scenario: captain status includes last_checkin_at after a check-in fires
- **WHEN** `captain(action="status")` is called after at least one Raven check-in has run
- **THEN** the response includes `last_checkin_at` as an ISO 8601 UTC string

#### Scenario: captain status last_checkin_at is null before any check-in
- **WHEN** `captain(action="status")` is called on a crew where no check-in has fired
- **THEN** `last_checkin_at` is `null`
