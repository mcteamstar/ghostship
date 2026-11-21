# auth/backend-login Specification

## Purpose

Defines backend login routes and their interactive and pasted credential workflows.

## Requirements

### Requirement: Login routes are per backend and per method
The transport SHALL expose one route per backend and method: `POST /login/kiro/{api-key|builder-id|identity-center}`, `POST /login/claude/{oauth|api-key|setup-token}` (plus `POST /login/claude/oauth/code`), and `POST /login/codex/{chatgpt|api-key}`. An unknown backend or method SHALL return HTTP 404. All login and logout routes SHALL sit behind the transport's bearer authentication.

#### Scenario: Unknown method
- **WHEN** `POST /login/codex/oauth` is called
- **THEN** the transport returns HTTP 404 and starts nothing

#### Scenario: Unauthenticated login rejected on keyed transport
- **WHEN** the transport has a bearer key configured and `POST /login/kiro/api-key` arrives without it
- **THEN** the transport returns HTTP 401 and stores nothing

### Requirement: Pasted credentials stored through their login route
`POST /login/{backend}/{api-key|setup-token}` SHALL take a JSON body `{"secret": "..."}`, store it as that backend's active credential and return the backend's status (no value) without starting any flow. An empty or missing secret SHALL be rejected with HTTP 400 and leave the stored credential unchanged.

#### Scenario: Store a Claude setup-token
- **WHEN** `POST /login/claude/setup-token` is called with `{"secret": "<token>"}`
- **THEN** the token is stored as claude's active credential and the response reports `method: setup-token`

#### Scenario: Empty secret rejected
- **WHEN** `POST /login/codex/api-key` is called with an empty `secret`
- **THEN** the transport returns HTTP 400 and the stored codex credential is unchanged

### Requirement: Login requires the backend to be enabled
`POST /login/{backend}/...` SHALL return HTTP 400 naming `GA_CREW_AGENT` when the backend is not enabled, and store or start nothing. `GET /login/{backend}` and `POST /logout/{backend}` SHALL work whether or not the backend is enabled.

#### Scenario: Login to a disabled backend
- **WHEN** codex is not in `GA_CREW_AGENT` and `POST /login/codex/api-key` is called
- **THEN** the transport returns HTTP 400 telling the operator to add codex to `GA_CREW_AGENT`, and stores nothing

#### Scenario: Logout from a disabled backend
- **WHEN** claude is not enabled but holds a stored credential and `POST /logout/claude` is called
- **THEN** the credential is removed

### Requirement: Bare login and logout paths are unassigned
The transport SHALL NOT serve any route at bare `/login` or `/logout` (any method). They are reserved for a future browser login page.

#### Scenario: Bare paths
- **WHEN** `GET /login`, `POST /login` or `POST /logout` is called
- **THEN** the transport returns HTTP 404

### Requirement: Logout cancels pending login flows

`POST /logout/{backend}` SHALL cancel the backend's pending flow and remove its login container before allowing a new flow to start.

#### Scenario: Logout cancels a pending login with nothing stored
- **WHEN** a kiro device login is pending, kiro holds no credential, and `POST /logout/kiro` is called
- **THEN** the transport returns HTTP 200 with `aborted_pending_login: true`, the login container is removed, and `GET /login/kiro` reports no pending flow

#### Scenario: A new login can start after cancelling
- **WHEN** a pending login was cancelled by `POST /logout/{backend}`
- **THEN** a following `POST /login/{backend}/{method}` starts a new flow instead of returning 409 for an already-pending flow

#### Scenario: Logout during login startup leaves no container
- **WHEN** `POST /logout/{backend}` cancels a flow whose login container is still being created
- **THEN** the login request that was starting the flow removes the container it created and reports the flow as cancelled, so no login container remains

#### Scenario: Logout while waiting for a login URL
- **WHEN** `POST /logout/{backend}` cancels a flow while its login request is still waiting for the login URL
- **THEN** that login request returns a cancelled error with no URL, removes its container, and does not clear a flow started after the cancel

#### Scenario: A cancelled flow cannot complete
- **WHEN** a pending login is cancelled by `POST /logout/{backend}` while a `GET /login/{backend}` poll is completing it
- **THEN** that poll does not store a credential, and `GET /login/{backend}` reports no credential and no pending flow

### Requirement: Launch starts the backend's interactive login when no credential is stored
When a crew is launched on a backend with no stored credential, the transport SHALL NOT create the crew. It SHALL start that backend's interactive login and return `not_authenticated` with its `login_url`, any `code`, and instructions to complete it and call launch again. kiro uses `identity-center` when Identity Center is configured, else `builder-id`; claude uses `oauth`; codex uses `chatgpt`.

#### Scenario: Kiro with Identity Center configured
- **WHEN** a kiro crew is launched, kiro has no stored credential, and `KIRO_IDENTITY_PROVIDER` and `KIRO_REGION` are configured
- **THEN** launch starts the Identity Center device-code flow with those values and returns `not_authenticated` with its `login_url` and `code`

#### Scenario: Kiro without Identity Center configured
- **WHEN** a kiro crew is launched, kiro has no stored credential, and no Identity Center settings are configured
- **THEN** launch starts the Builder ID device-code flow and returns `not_authenticated` with its `login_url` and `code`

#### Scenario: Codex without credential
- **WHEN** a codex crew is launched and codex has no stored credential
- **THEN** launch starts the ChatGPT device-code flow and returns `not_authenticated` with its `login_url` and `code`, and creates no crew container

#### Scenario: Claude without credential
- **WHEN** a claude crew is launched and claude has no stored credential
- **THEN** launch starts the Claude authorisation-code flow and returns `not_authenticated` with its `login_url`; the code is submitted through `POST /login/claude/oauth/code`

#### Scenario: Flow already pending
- **WHEN** a crew is launched while that backend's login flow is already pending
- **THEN** launch returns `not_authenticated` with the pending flow's `login_url` rather than starting a second flow

#### Scenario: Stored credential skips login
- **WHEN** a crew is launched and its backend holds any stored credential, including an API key
- **THEN** no login flow is started and the crew is created with that credential

### Requirement: First-time device auth flow
The system SHALL initiate a kiro-cli device auth flow inside the crew container when no `ga-kiro-auth` file exists (or it exists but is empty), and return a login URL (and code, if available) instead of finishing crew setup.

#### Scenario: No auth file exists
- **WHEN** `launch` is called, `DATA_DIR/ga-kiro-auth` does not exist or is empty, and no currently running crew can supply auth rows as a fallback
- **THEN** the system starts `kiro-cli login --use-device-flow` (plus the `--license`/identity-provider/region flags for the login method) inside the crew container, registers the crew with status `auth_required` and the returned login URL, and returns that status to the caller without minting a cookie

#### Scenario: Resuming after auth
- **WHEN** `launch` is called again with the same `crew_id` whose registry status is `auth_required`
- **THEN** the system checks the crew container's kiro-cli database for completed auth; if found, it writes the auth rows to `ga-kiro-auth` and proceeds to finish crew setup; if not found, it returns the same `auth_required` status and login URL again

### Requirement: Kiro auth state transitions
The transport SHALL track kiro auth as unauthenticated, pending or authenticated, from whether kiro holds an active credential. `POST /login/kiro/builder-id` or `POST /login/kiro/identity-center` moves to pending; `GET /login/kiro` completing moves to authenticated; `POST /login/kiro/api-key` moves to authenticated; `POST /logout/kiro` moves to unauthenticated from either state, cancelling any pending flow. The transport SHALL NOT make any other transition.

#### Scenario: Device login allowed when already authenticated
- **WHEN** a kiro device login is started and kiro already holds a credential
- **THEN** the flow starts, and the existing credential is replaced only when the flow completes

#### Scenario: Cannot login when login already in progress
- **WHEN** a kiro device login is started while a kiro flow is already pending
- **THEN** the transport returns HTTP 409 with a message indicating a login is already in progress and `GET /login/kiro` should be polled

#### Scenario: Auth injected into running kiro crews on login completion
- **WHEN** `GET /login/kiro` first returns `status: "complete"`
- **THEN** the transport has stored kiro's credential with mode `0600` and has injected the fresh auth rows into every crew whose registry status is `running` and whose `acp_backend` is `kiro` (an absent `acp_backend` counts as kiro), without restarting those crews; running claude and codex crews are not modified

#### Scenario: Orphaned temp containers cleaned up on startup
- **WHEN** the transport starts and one or more containers named `ga-login-*` exist
- **THEN** those containers are stopped and removed during `_reconcile_registry` before any other operations

#### Scenario: Logout leaves running crews untouched
- **WHEN** `POST /logout/kiro` is called while kiro holds a device-flow credential and kiro crews are running
- **THEN** the stored credential is deleted, and no running crew's kiro-cli database is modified

#### Scenario: Logout from pending
- **WHEN** a kiro device login is pending and `POST /logout/kiro` is called
- **THEN** the flow is cancelled, its login container removed, and kiro auth is unauthenticated

### Requirement: Kiro login method selects the identity provider
`identity-center` SHALL run `kiro-cli login` with `--identity-provider`, `--region` and `--license pro`, using the start URL and region from the request, or else the configured `KIRO_IDENTITY_PROVIDER` and `KIRO_REGION`. `builder-id` SHALL run it with `--use-device-flow` and `--license free`. The `--license` value SHALL be derived from the method and SHALL NOT be configurable. A kiro `api-key` credential SHALL skip the device flow. Claude and Codex crews SHALL receive no kiro auth.

#### Scenario: Identity Center flow
- **WHEN** `POST /login/kiro/identity-center` is called with a start URL and a region
- **THEN** the `kiro-cli login` command includes `--identity-provider <start URL>`, `--region <region>` and `--license pro`

#### Scenario: Identity Center from configuration
- **WHEN** `POST /login/kiro/identity-center` is called with no start URL or region and `KIRO_IDENTITY_PROVIDER` and `KIRO_REGION` are configured
- **THEN** the Identity Center flow runs with the configured values

#### Scenario: Identity Center flow missing inputs
- **WHEN** `POST /login/kiro/identity-center` is called with no start URL or region and none configured
- **THEN** the transport returns HTTP 400 naming the missing input and starts no container

#### Scenario: Builder ID flow
- **WHEN** `POST /login/kiro/builder-id` is called
- **THEN** `kiro-cli login` runs with only `--use-device-flow`; if kiro-cli shows a login-method selection menu first, the system answers it to select Builder ID and the flow still completes with a device code and URL

#### Scenario: Kiro API key — device flow skipped
- **WHEN** kiro's active method is `api-key` and `launch` is called for a kiro crew
- **THEN** the system does NOT start a device flow and does NOT inject kiro-cli auth rows into the crew's SQLite DB
- **THEN** the stored key is passed as `KIRO_API_KEY` to the crew container at creation time

#### Scenario: Kiro device credential — unchanged injection
- **WHEN** kiro's active method is a device-code method and a kiro crew is launched
- **THEN** the stored kiro-cli login state is injected into the crew as before

#### Scenario: Claude or Codex backend — no kiro auth state required
- **WHEN** a claude or codex crew is launched and kiro holds no credential
- **THEN** `launch` proceeds without requiring kiro auth state

### Requirement: Concurrent login guard is atomic
The system SHALL hold the login-pending lock across both the auth-file guard check and the _login_pending guard check, so that two concurrent POST /login requests cannot both pass both guards and start duplicate login containers.

#### Scenario: Concurrent login requests are serialised
- **WHEN** two POST /login requests arrive simultaneously and no login is in progress
- **THEN** exactly one proceeds to start a login container; the other receives a 409 response indicating a login is already in progress

#### Scenario: Sequential login check is consistent
- **WHEN** a POST /login request checks both the auth-file guard and the login-pending guard
- **THEN** both checks are evaluated while holding the same lock, so a concurrent request cannot slip through between the two checks
