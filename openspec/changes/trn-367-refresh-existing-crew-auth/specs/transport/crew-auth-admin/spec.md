# Spec Delta

## Purpose

Provides authenticated operator APIs for refreshing the credential assigned to an existing crew and reporting when refresh requires a later wake or workspace-preserving recreation.

## ADDED Requirements

### Requirement: Operator can refresh a crew's assigned credential
The transport SHALL expose `POST /crews/{crew_id}/auth/refresh` for bearer-authenticated operator clients and `POST /internal/crews/{crew_id}/auth/refresh` for trusted portside callers. Both endpoints SHALL perform the same refresh operation for the credential recorded for that crew's backend and profile, return the same outcome, and accept no credential in the request.

#### Scenario: Operator API refreshes a running flow-auth crew
- **WHEN** an authenticated operator refreshes a running crew with a stored flow credential
- **THEN** the transport injects the current credential for the crew's recorded backend and profile and returns `status: refreshed`

#### Scenario: Radar uses the internal endpoint
- **WHEN** a caller presents a valid `X-Transport-Token` to `POST /internal/crews/{crew_id}/auth/refresh`
- **THEN** the transport performs the same refresh operation and returns the same outcome as the operator endpoint

#### Scenario: Unknown crew
- **WHEN** either endpoint is called for a crew that is not in the registry
- **THEN** the transport returns HTTP 404 without changing any crew or credential state

### Requirement: Refresh reports a safe outcome for crew state and credential method
The refresh operation SHALL report whether a crew was updated, will receive its flow credential on wake, already has its static credential, or requires recreation because its static credential or method changed. It SHALL NOT start, stop, or recreate a crew.

#### Scenario: Stopped flow-auth crew
- **WHEN** an operator refreshes a stopped crew with a stored flow credential
- **THEN** the transport returns `status: pending_on_wake` and the crew remains stopped

#### Scenario: Static credential matches the container
- **WHEN** an operator refreshes a crew whose stored static credential and method match its container configuration
- **THEN** the transport returns `status: current` without changing the container

#### Scenario: Static credential or method differs
- **WHEN** an operator refreshes a crew whose stored static credential or method differs from its container configuration
- **THEN** the transport returns `status: recreate_required` with workspace-preserving recovery guidance and does not start, stop, or recreate the crew

#### Scenario: Credential is missing
- **WHEN** the recorded backend and profile have no stored credential
- **THEN** the transport returns `status: credential_missing` and does not alter the crew

#### Scenario: Flow credential injection fails
- **WHEN** injection of the current flow credential into a running crew fails
- **THEN** the transport returns `status: refresh_failed` with a safe, actionable error and leaves the crew running

### Requirement: Refresh APIs protect credential and transport secrets
The operator endpoint SHALL require bearer authentication when API-key auth is enabled and SHALL reject browser-origin requests. The internal endpoint SHALL require a valid `X-Transport-Token`. Neither endpoint SHALL return or log credential values.

#### Scenario: Unauthenticated operator request
- **WHEN** `POST /crews/{crew_id}/auth/refresh` is called without a valid bearer token while API-key auth is enabled
- **THEN** the transport rejects the request before refreshing credentials

#### Scenario: Browser request to operator endpoint
- **WHEN** `POST /crews/{crew_id}/auth/refresh` includes an `Origin` header
- **THEN** the transport rejects the request and makes no credential changes

#### Scenario: Missing internal transport token
- **WHEN** `POST /internal/crews/{crew_id}/auth/refresh` is called without a valid `X-Transport-Token`
- **THEN** the transport returns HTTP 401 and performs no refresh

#### Scenario: Refresh result contains no secret
- **WHEN** either endpoint returns any refresh outcome
- **THEN** the response and logs contain no credential value or transport token
