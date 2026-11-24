# Spec Delta

## ADDED Requirements

### Requirement: Radar exposes the crew auth refresh operation
Radar SHALL provide an operator action for each crew and a browser-facing `POST /api/crews/{crew_id}/auth/refresh` endpoint. The endpoint SHALL proxy to the transport's internal refresh API using `X-Transport-Token` and return the transport outcome without modification.

#### Scenario: Operator refreshes auth from a crew detail panel
- **WHEN** an operator selects the auth refresh action for a crew in Radar
- **THEN** the browser calls `POST /api/crews/{crew_id}/auth/refresh` and Radar proxies it to `POST /internal/crews/{crew_id}/auth/refresh`
- **THEN** Radar displays the returned outcome, including pending-on-wake or recreate-required guidance

#### Scenario: Transport is unavailable during refresh
- **WHEN** Radar cannot reach the transport while proxying a refresh request
- **THEN** Radar returns HTTP 502 with a safe transport-unavailable message and displays that refresh did not complete

### Requirement: Portal session gates the Radar auth refresh action
Caddy SHALL route `POST /api/crews/{crew_id}/auth/refresh` through the existing Radar session gate. When API-key auth is configured, the browser action SHALL require a valid `gs_session` cookie.

#### Scenario: Authenticated portal operator refreshes a crew
- **WHEN** a valid portal session calls `POST /api/crews/{crew_id}/auth/refresh`
- **THEN** Caddy forwards the request to Radar

#### Scenario: Unauthenticated portal request
- **WHEN** the refresh action is requested without a valid portal session and API-key auth is configured
- **THEN** Caddy redirects the browser to `/dashboard/login` and does not forward the request to Radar
