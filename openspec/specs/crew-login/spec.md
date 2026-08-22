# Crew Login Specification

## Purpose

Exposes operator-facing HTTP endpoints on the transport server for authenticating and de-authenticating the Ghost Academy via kiro-cli device flow. The operator never needs to SSH into a container or name a specific crew — login spins up its own ephemeral container, extracts the auth rows on completion, propagates them to all running crews, then tears itself down.

## Requirements

### Requirement: POST /login initiates device auth via a dedicated ephemeral container
The system SHALL expose a `POST /login` route on the transport's MCP port that creates a short-lived container named `ga-login-<token>` (not registered in the crew registry), allocates a pseudo-TTY via the Podman exec API, launches `kiro-cli login` with the configured license/identity-provider/region flags, and returns the device code and URL extracted from the process output. The endpoint SHALL return HTTP 409 when `ga-kiro-auth` already exists and is non-empty, or when a login flow is already pending. The endpoint SHALL NOT be registered as an MCP tool and SHALL NOT appear in the MCP tool list.

#### Scenario: Login initiated successfully
- **WHEN** `POST /login` is called and the academy is unauthenticated with no pending flow
- **THEN** a `ga-login-<token>` container is started, the response includes `status: "pending"`, `login_url`, and `code` extracted from the kiro-cli output, and the login process continues running in the background inside the container

#### Scenario: Already authenticated
- **WHEN** `POST /login` is called and `ga-kiro-auth` exists and is non-empty
- **THEN** the response returns HTTP 409 with a message indicating the academy is already authenticated and `POST /logout` must be called first

#### Scenario: Login already in progress
- **WHEN** `POST /login` is called while a login flow is pending
- **THEN** the response returns HTTP 409 with a message indicating a login is already in progress and `GET /login` should be polled

#### Scenario: Login process fails to produce a URL
- **WHEN** `POST /login` is called but kiro-cli exits before printing a URL
- **THEN** the temp container is nuked, `_login_pending` is cleared, and the response returns HTTP 500 with the captured output so the operator can diagnose

#### Scenario: API-key authentication applies
- **WHEN** `GA_API_KEY` is configured and `POST /login` is called without a valid bearer token
- **THEN** the transport responds with `401 Unauthorized`

### Requirement: GET /login polls auth completion and propagates on success
The system SHALL expose a `GET /login` route that checks whether kiro-cli auth has completed inside the temp container by inspecting its SQLite database for a full auth row set. On completion, the transport SHALL write `ga-kiro-auth`, inject the auth rows into every running crew's kiro-cli DB, and nuke the temp container.

#### Scenario: No login in progress
- **WHEN** `GET /login` is called and `_login_pending` is None
- **THEN** the response returns HTTP 404

#### Scenario: Auth still in progress
- **WHEN** `GET /login` is called and the temp container's kiro-cli DB contains only a device-registration row (or no rows)
- **THEN** the response returns `status: "pending"`

#### Scenario: Auth completed
- **WHEN** `GET /login` is called and the temp container's kiro-cli DB contains a full token row set
- **THEN** the transport writes `ga-kiro-auth` with mode `0600`, injects auth rows into all running crews, nukes the temp container, clears `_login_pending`, and the response returns `status: "complete"`

### Requirement: POST /logout clears academy auth globally
The system SHALL expose a `POST /logout` route that deletes `ga-kiro-auth` and executes `DELETE FROM auth_kv` in every running crew's kiro-cli SQLite DB. The endpoint SHALL return HTTP 404 when the academy is not authenticated.

#### Scenario: Logout when authenticated
- **WHEN** `POST /logout` is called and `ga-kiro-auth` exists and is non-empty
- **THEN** `ga-kiro-auth` is deleted, `DELETE FROM auth_kv` is executed in every running crew's DB, and the response returns `status: "logged_out"`

#### Scenario: Logout when not authenticated
- **WHEN** `POST /logout` is called and `ga-kiro-auth` does not exist or is empty
- **THEN** the response returns HTTP 404
