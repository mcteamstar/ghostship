## MODIFIED Requirements

### Requirement: POST /login initiates device auth via a dedicated ephemeral container
The system SHALL expose a `POST /login` route on the transport's MCP port that creates a short-lived container named `ga-login-<token>` (not registered in the crew registry), allocates a pseudo-TTY via the Podman exec API, launches `kiro-cli login` with the configured license/identity-provider/region flags, and returns the device code and URL extracted from the process output. When `kiro-cli` presents an interactive login-method selection menu before any identity-provider prompt (the path taken when no identity provider is configured), the system SHALL detect that menu and answer it by accepting the default (Builder ID) option, then continue watching for the device code and URL as normal. The endpoint SHALL return HTTP 409 when `ga-kiro-auth` already exists and is non-empty, or when a login flow is already pending. The endpoint SHALL NOT be registered as an MCP tool and SHALL NOT appear in the MCP tool list.

The endpoint SHALL set `_login_pending` to a non-None sentinel value while still holding `_login_pending_lock`, immediately after both guard checks pass and before releasing the lock. No code path between the guard checks and the sentinel write SHALL release the lock.

#### Scenario: Login initiated successfully
- **WHEN** `POST /login` is called and the academy is unauthenticated with no pending flow
- **THEN** a `ga-login-<token>` container is started, `_login_pending` is set to a non-None sentinel before the lock is released, the response includes `status: "pending"`, `login_url`, and `code` extracted from the kiro-cli output, and the login process continues running in the background inside the container

#### Scenario: Login-method selection menu appears (no identity provider configured)
- **WHEN** `POST /login` is called with no `KIRO_IDENTITY_PROVIDER` configured, and `kiro-cli login --use-device-flow` prints an interactive "Select login method" menu (Builder ID / Google / GitHub / Your Organization) before any device code
- **THEN** the system recognizes the menu, sends the input needed to accept the default Builder ID option, and the login proceeds to produce a device code and URL within the existing timeout — the request does NOT return HTTP 500 for this reason

#### Scenario: Already authenticated
- **WHEN** `POST /login` is called and `ga-kiro-auth` exists and is non-empty
- **THEN** the response returns HTTP 409 with a message indicating the academy is already authenticated and `POST /logout` must be called first

#### Scenario: Login already in progress
- **WHEN** `POST /login` is called while a login flow is pending
- **THEN** the response returns HTTP 409 with a message indicating a login is already in progress and `GET /login` should be polled

#### Scenario: Concurrent POST /login requests are serialised
- **WHEN** two `POST /login` requests arrive simultaneously with no pending flow and no existing auth
- **THEN** exactly one request proceeds and starts a container; the other observes the sentinel and returns HTTP 409

#### Scenario: Login process fails to produce a URL
- **WHEN** `POST /login` is called but kiro-cli exits before printing a URL
- **THEN** the temp container is nuked, `_login_pending` is cleared, and the response returns HTTP 500 with the captured output so the operator can diagnose

#### Scenario: API-key authentication applies
- **WHEN** `GA_API_KEY` is configured and `POST /login` is called without a valid bearer token
- **THEN** the transport responds with `401 Unauthorized`
