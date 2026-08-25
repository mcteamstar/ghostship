# Crew Login Specification

## Purpose

Exposes operator-facing HTTP endpoints on the transport server for authenticating and de-authenticating the Ghost Academy via kiro-cli device flow. The operator never needs to SSH into a container or name a specific crew — login spins up its own ephemeral container, extracts the auth rows on completion, propagates them to all running crews, then tears itself down.

## Requirements

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

#### Scenario: Login flow initiated from within launch (no existing pending flow)
- **WHEN** `launch` is called without valid auth, no login flow is currently pending, and `_initiate_login()` is called internally
- **THEN** a `ga-login-<token>` container is started, `_login_pending` is set to a non-None sentinel before the lock is released (same TOCTOU guard as a direct `POST /login` call), and `login_url` and `code` are extracted and returned to the caller via the `launch` error response — the background drain thread continues running to completion

#### Scenario: Login flow initiated from within launch (flow already pending)
- **WHEN** `launch` is called without valid auth and a login flow is already in progress (the `_login_pending` sentinel is set)
- **THEN** `launch` does NOT start a second container; the response includes `error: "not_authenticated"` and `login_pending: true` so the caller knows to poll `GET /login`

### Requirement: GET /login polls auth completion and propagates on success
The system SHALL expose a `GET /login` route that checks whether kiro-cli auth has completed inside the temp container by inspecting its SQLite database for a full auth row set. On completion, the transport SHALL write `ga-kiro-auth`, inject the auth rows into every running crew's kiro-cli DB, and nuke the temp container.

When clearing `_login_pending`, the handler SHALL verify that the container name in `_login_pending` matches the container it just completed. If `_login_pending` references a different container (a new login started concurrently), the handler SHALL NOT clear it.

#### Scenario: No login in progress
- **WHEN** `GET /login` is called and `_login_pending` is None
- **THEN** the response returns HTTP 404

#### Scenario: Auth still in progress
- **WHEN** `GET /login` is called and the temp container's kiro-cli DB contains only a device-registration row (or no rows)
- **THEN** the response returns `status: "pending"`

#### Scenario: Auth completed
- **WHEN** `GET /login` is called and the temp container's kiro-cli DB contains a full token row set
- **THEN** the transport writes `ga-kiro-auth` with mode `0600`, injects auth rows into all running crews, nukes the temp container, clears `_login_pending` only if its container name matches, and the response returns `status: "complete"`

#### Scenario: Concurrent login started between nuke and clear
- **WHEN** `GET /login` completes a login flow but a new `POST /login` has set `_login_pending` to a different container between nuke and the clear attempt
- **THEN** the handler does NOT clear `_login_pending` and the new login flow proceeds undisturbed

### Requirement: POST /logout clears academy auth globally
The system SHALL expose a `POST /logout` route that deletes `ga-kiro-auth` and executes `DELETE FROM auth_kv` in every running crew's kiro-cli SQLite DB. The endpoint SHALL return HTTP 404 when the academy is not authenticated.

#### Scenario: Logout when authenticated
- **WHEN** `POST /logout` is called and `ga-kiro-auth` exists and is non-empty
- **THEN** `ga-kiro-auth` is deleted, `DELETE FROM auth_kv` is executed in every running crew's DB, and the response returns `status: "logged_out"`

#### Scenario: Logout when not authenticated
- **WHEN** `POST /logout` is called and `ga-kiro-auth` does not exist or is empty
- **THEN** the response returns HTTP 404

### Requirement: Admiral mail signature verification is reliable
The `verify-admiral-sig` script SHALL strip trailing whitespace from the parsed mail body before computing the expected HMAC, matching how the transport signs the body before delivery.

#### Scenario: Captain order with valid signature is accepted
- **WHEN** Raven reads a captain mailbox message sent by the transport via `_format_captain_mail`
- **THEN** `verify-admiral-sig` exits 0 and Raven treats the message as a genuine Admiral standing order

#### Scenario: Captain order with invalid signature is rejected
- **WHEN** a message in the captain mailbox has a forged or missing `X-Admiral-Sig` header
- **THEN** `verify-admiral-sig` exits 1 and Raven does not act on it
