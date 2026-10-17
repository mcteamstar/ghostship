# Spec Delta

## ADDED Requirements

### Requirement: Kiro auth state machine
The transport SHALL track kiro auth as unauthenticated, pending or authenticated, from whether kiro holds an active credential. `POST /login/kiro/builder-id` or `POST /login/kiro/identity-center` moves to pending; `GET /login/kiro` completing moves to authenticated; `POST /login/kiro/api-key` moves to authenticated; `POST /logout/kiro` moves to unauthenticated. The transport SHALL NOT make any other transition.

#### Scenario: Device login allowed when already authenticated
- **WHEN** a kiro device login is started and kiro already holds a credential
- **THEN** the flow starts, and the existing credential is replaced only when the flow completes

#### Scenario: Cannot login when login already in progress
- **WHEN** a kiro device login is started while a kiro flow is already pending
- **THEN** the transport returns HTTP 409 with a message indicating a login is already in progress and `GET /login/kiro` should be polled

#### Scenario: Auth injected into all running crews on login completion
- **WHEN** `GET /login/kiro` first returns `status: "complete"`
- **THEN** the transport has stored kiro's credential with mode `0600` and has injected the fresh auth rows into every crew whose registry status is `running`, without restarting those crews

#### Scenario: Auth cleared from all running crews on logout
- **WHEN** `POST /logout/kiro` is called and kiro holds a device-flow credential
- **THEN** the credential is deleted and the transport has executed `DELETE FROM auth_kv` in every running crew's kiro-cli SQLite DB

#### Scenario: Orphaned temp containers cleaned up on startup
- **WHEN** the transport starts and one or more containers named `ga-login-*` exist
- **THEN** those containers are stopped and removed during `_reconcile_registry` before any other operations

### Requirement: Kiro login method selects the identity provider
`identity-center` SHALL run `kiro-cli login` with `--identity-provider`, `--region` and `--license pro`, using the start URL and region from the request, or else the configured `KIRO_IDENTITY_PROVIDER` and `KIRO_REGION`. `builder-id` SHALL run it with only `--use-device-flow`. A kiro `api-key` credential SHALL skip the device flow. Claude and Codex crews SHALL receive no kiro auth.

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

## REMOVED Requirements

### Requirement: Academy auth state machine
**Reason**: Replaced by "Kiro auth state machine": state comes from the credential store, a device login may start while a credential is held (completion replaces it), and logout moves to `POST /logout/kiro`.
**Migration**: Use `ghostship auth login kiro` and `ghostship auth logout kiro`.

### Requirement: Identity provider configuration
**Reason**: Replaced by "Kiro login method selects the identity provider" and backend-credentials: the Kiro method (API key, Builder ID, Identity Center) is explicit and Identity Center settings may come from the request or configuration, and the Claude/Codex precedence chains are replaced by one active credential.
**Migration**: None; `KIRO_IDENTITY_PROVIDER` and `KIRO_REGION` in `ghostship.conf` keep selecting Identity Center.
