# Crew Login Specification

## Purpose

Exposes operator-facing HTTP endpoints on the transport server for authenticating and de-authenticating the Ghost Academy via kiro-cli device flow. The operator never needs to SSH into a container or name a specific crew — login spins up its own ephemeral container, extracts the auth rows on completion, propagates them to all running crews, then tears itself down.

## Requirements

### Requirement: Abandoned kiro login flows expire without polling

An in-progress kiro login flow (`_login_pending` is non-None) that has not completed within 900 seconds of starting SHALL be expired by a periodic maintenance sweep, independent of whether `GET /login` is polled. On expiry the transport SHALL stop and remove the associated `ga-login-<token>` container (best-effort) and clear `_login_pending`.

#### Scenario: Abandoned kiro flow is expired by the maintenance sweep
- **GIVEN** a kiro login flow has been pending for more than 900 seconds
- **WHEN** the periodic maintenance sweep runs
- **THEN** the `ga-login-<token>` container is stopped and removed and `_login_pending` is set to None — a subsequent `POST /login` is accepted

#### Scenario: Active kiro flow is not expired prematurely
- **GIVEN** a kiro login flow started less than 900 seconds ago
- **WHEN** the periodic maintenance sweep runs
- **THEN** `_login_pending` is unchanged and the container is not removed

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

### Requirement: Admiral mail signature verification is reliable

The `verify-admiral-sig` script SHALL construct the verification payload using the
canonical length-prefixed encoding defined in `admiral-sig/payload-format`. It SHALL NOT
strip, normalize, or otherwise modify the body before payload construction. It SHALL
exit 1 cleanly when the message is multipart (i.e., `get_payload()` returns a non-string
value) rather than raising an unhandled exception.

#### Scenario: Captain order with valid signature is accepted

- **WHEN** Raven reads a captain mailbox message sent by the transport via `_format_captain_mail`
- **THEN** `verify-admiral-sig` exits 0 and Raven treats the message as a genuine Admiral
  standing order

#### Scenario: Captain order with invalid signature is rejected

- **WHEN** a message in the captain mailbox has a forged or missing `X-Admiral-Sig` header
- **THEN** `verify-admiral-sig` exits 1 and Raven does not act on it

#### Scenario: Multipart message is rejected cleanly

- **WHEN** `verify-admiral-sig` processes a MIME multipart message
- **THEN** it exits 1 without raising an unhandled exception

### Requirement: POST /login/kiro initiates device auth via a dedicated ephemeral container
The system SHALL expose `POST /login/kiro/builder-id` and `POST /login/kiro/identity-center` routes on the transport's MCP port, replacing `POST /login`. Each creates a short-lived container named `ga-login-<token>` (not registered in the crew registry), allocates a pseudo-TTY via the Podman exec API, launches `kiro-cli login` with the flags for its method (`identity-center` with the start URL and region from the request body or configuration; `builder-id` with only `--use-device-flow`), and returns the device code and URL extracted from the process output. When `kiro-cli` presents an interactive login-method selection menu before any identity-provider prompt (the path taken for `builder-id`), the system SHALL detect that menu and answer it by accepting the default (Builder ID) option, then continue watching for the device code and URL as normal. The endpoint SHALL return HTTP 409 when a login flow is already pending. An existing kiro credential SHALL NOT block the flow; it is replaced when the flow completes. The endpoint SHALL NOT be registered as an MCP tool and SHALL NOT appear in the MCP tool list.

The PTY read loop SHALL wait up to 45 seconds for kiro-cli to print the device URL. This accounts for the network round-trip kiro-cli makes to the identity provider to register the device after the user answers the Start URL and Region prompts; this call typically takes a few seconds but can be slower on high-latency links.

Before the PTY output loop begins, any bytes received in the same network chunk as the HTTP 101 upgrade response headers SHALL be prepended to the accumulated PTY output, so no login URL printed in that initial burst is discarded. The raw socket used for the exec SHALL have a socket timeout applied before the first read so that a hung Podman socket does not block the transport indefinitely.

#### Scenario: Login initiated successfully
- **WHEN** `POST /login/kiro/builder-id` is called with no pending flow
- **THEN** a `ga-login-<token>` container is started, `_login_pending` is set to a non-None sentinel before the lock is released, the response includes `status: "pending"`, `login_url`, and `code` extracted from the kiro-cli output, and the login process continues running in the background inside the container

#### Scenario: Login-method selection menu appears (no identity provider configured)
- **WHEN** `POST /login/kiro/builder-id` is called, and `kiro-cli login --use-device-flow` prints an interactive "Select login method" menu (Builder ID / Google / GitHub / Your Organization) before any device code
- **THEN** the system recognizes the menu, sends the input needed to accept the default Builder ID option, and the login proceeds to produce a device code and URL within the existing timeout — the request does NOT return HTTP 500 for this reason

#### Scenario: Already authenticated
- **WHEN** `POST /login/kiro/builder-id` is called and kiro already holds a credential
- **THEN** the flow starts as normal, and the existing credential remains active until the new flow completes

#### Scenario: Login already in progress
- **WHEN** `POST /login/kiro/builder-id` is called while a login flow is pending
- **THEN** the response returns HTTP 409 with a message indicating a login is already in progress and `GET /login/kiro` should be polled

#### Scenario: Concurrent POST /login requests are serialised
- **WHEN** two `POST /login/kiro/builder-id` requests arrive simultaneously with no pending flow
- **THEN** exactly one request proceeds and starts a container; the other observes the sentinel and returns HTTP 409

#### Scenario: Login process fails to produce a URL
- **WHEN** `POST /login/kiro/builder-id` is called but kiro-cli exits before printing a URL
- **THEN** the temp container is nuked, `_login_pending` is cleared, and the response returns HTTP 500 with the captured output so the operator can diagnose

#### Scenario: API-key authentication applies
- **WHEN** `GA_API_KEY` is configured and `POST /login/kiro/builder-id` is called without a valid bearer token
- **THEN** the transport responds with `401 Unauthorized`

#### Scenario: Login flow initiated from within launch (no existing pending flow)
- **WHEN** `launch` is called without valid auth, no login flow is currently pending, and `_initiate_login()` is called internally
- **THEN** a `ga-login-<token>` container is started, `_login_pending` is set to a non-None sentinel before the lock is released (same TOCTOU guard as a direct `POST /login/kiro/builder-id` call), and `login_url` and `code` are extracted and returned to the caller via the `launch` error response — the background drain thread continues running to completion

#### Scenario: Login flow initiated from within launch (flow already pending)
- **WHEN** `launch` is called without valid auth and a login flow is already in progress (the `_login_pending` sentinel is set)
- **THEN** `launch` does NOT start a second container; the response includes `error: "not_authenticated"` and `login_pending: true` so the caller knows to poll `GET /login/kiro`

#### Scenario: Login URL present in the same chunk as the 101 headers is not lost
- **GIVEN** the PTY exec socket
- **WHEN** the Podman daemon sends the HTTP 101 upgrade headers and the first bytes of PTY output (including the login URL) in a single TCP segment
- **THEN** the transport returns the login URL correctly in the response — it is not silently discarded

#### Scenario: Hung exec socket does not block indefinitely
- **WHEN** the Podman exec socket is established but no data arrives
- **THEN** the socket read raises a timeout error after no more than 120 seconds, and the login flow fails with an appropriate error rather than blocking the transport forever
