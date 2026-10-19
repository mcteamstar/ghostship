## ADDED Requirements

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

### Requirement: Kiro auth reused across crews
The system SHALL read the saved `ga-kiro-auth` file and inject its rows into every subsequent crew's kiro-cli database, so a single login authenticates all future crews without repeating the device auth flow. `ga-kiro-auth` is a single plain file under `DATA_DIR`, mode `0600` — not a Podman secret — so reading it never involves Podman's secret API or file-driver backing store.

#### Scenario: Auth file has content
- **WHEN** `launch` creates a new crew and `DATA_DIR/ga-kiro-auth` exists with content
- **THEN** the system injects the decoded auth rows into the new crew's kiro-cli SQLite database during setup, with no login prompt shown to the caller

#### Scenario: Auth file is created or refreshed
- **WHEN** a completed device-auth flow creates or replaces the auth file
- **THEN** the file is written in place with mode `0600`, flushed, for later launches to read

#### Scenario: No fallback to running crews
- **WHEN** a kiro crew is launched and kiro holds no stored credential, while other kiro crews are running and authenticated
- **THEN** the launch does not read auth from any running crew; it starts kiro's interactive login as for any unauthenticated launch

## REMOVED Requirements

### Requirement: Kiro auth state machine
**Reason**: Logout no longer clears auth from running crews (logout acts on the transport only — running crews keep their launch-time credential). Since TRN-259 running crews may also be claude or codex crews, so login completion now injects only into kiro crews. Replaced by "Kiro auth state transitions", which is otherwise unchanged.
**Migration**: None for operators. A running crew stays authenticated after `ghostship auth logout kiro`; relaunch or nuke it to drop its credential.

### Requirement: Auth reuse across crews
**Reason**: Its "auth file missing or empty" scenario let a launch take kiro auth from any running crew. Logout no longer touches running crews, so that fallback would undo a logout at the next launch. The transport has not read running crews since TRN-233 (the credential store is the source of truth). Replaced by "Kiro auth reused across crews" without that scenario.
**Migration**: None. Matches current behaviour.
