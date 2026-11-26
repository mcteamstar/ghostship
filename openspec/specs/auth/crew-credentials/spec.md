# auth/crew-credentials Specification

## Purpose

Defines credential resolution, delivery and authentication during a crew lifecycle.

## Requirements

### Requirement: Logout leaves running crews unchanged

Logout SHALL NOT modify running crews or the credentials they received at launch.

#### Scenario: Running crews are left alone
- **WHEN** `POST /logout/{backend}` is called while crews of that backend are running
- **THEN** no running crew is executed into, restarted or stopped, and each keeps the credential it launched with until it is relaunched

### Requirement: Credentials resolved at each crew launch
The transport SHALL read a backend's active credential from the store when it launches a crew, not once at startup. A credential stored, replaced or cleared SHALL take effect for the next crew launch without restarting the transport. Running crews SHALL keep their launch-time credential unless a login-flow completion or an explicit operator refresh successfully injects the current flow credential for their recorded backend and profile. Static credentials SHALL remain fixed in the container environment; a changed or replaced static credential or method SHALL require workspace-preserving crew recreation.

#### Scenario: Rotation without restart
- **WHEN** a new claude API key is stored while the transport is running and a claude crew is then launched
- **THEN** the new crew receives the new key, with no transport restart or reinstall

#### Scenario: Logout takes effect at the next launch
- **WHEN** a backend is logged out while one of its crews is running, and a new crew of that backend is then launched
- **THEN** the running crew keeps the credential it already received, and the new crew receives no credential and starts that backend's login instead

#### Scenario: Flow credential refresh applies to matching running crew
- **WHEN** a login-flow credential completes or an operator refreshes a crew assigned to that backend and profile
- **THEN** the current flow credential is injected into that running crew
- **AND** crews assigned to a different backend or profile are not modified

#### Scenario: Changed static credential requires recreation
- **WHEN** a stored static credential or its method changes after a crew container was created
- **THEN** the existing container keeps its launch-time environment and the operator is told that the crew must be recreated with its workspace preserved

### Requirement: Credential delivered to crews according to its method
At crew launch the transport SHALL deliver only the backend's active credential. `api-key` (kiro, claude, codex) SHALL be set as `KIRO_API_KEY`, `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` respectively. Claude `setup-token` SHALL be set as `CLAUDE_CODE_OAUTH_TOKEN`. Kiro device-flow, Claude authorisation-code and Codex `chatgpt` credentials SHALL be installed as the CLI's login state inside the crew (for codex, `~/.codex/auth.json`).

#### Scenario: Exactly one Claude credential reaches the crew
- **WHEN** claude's active method is `setup-token` and a claude crew launches
- **THEN** the crew has `CLAUDE_CODE_OAUTH_TOKEN` set, and has neither `ANTHROPIC_API_KEY` nor an installed `~/.claude/` login

#### Scenario: Codex ChatGPT credential reaches the crew as login state
- **WHEN** codex's active method is `chatgpt` and a codex crew launches
- **THEN** the crew's `~/.codex/auth.json` holds the stored login and `OPENAI_API_KEY` is not set

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

### Requirement: Crew secrets not persisted in plaintext after injection

After injection, `crews.json` SHALL store only non-reversible identifiers for the Admiral public key and `policy_signing_key`, never their plaintext. The private key SHALL exist only at `DATA_DIR/secrets/<crew_id>.admiral_secret`; the public key MAY be retained for reference.

#### Scenario: crews.json entry does not contain plaintext admiral_secret after launch

- **WHEN** a crew is launched and `_finish_crew_setup` completes successfully
- **THEN** the `crews.json` entry contains no plaintext private key material; at most a
  non-reversible identifier is stored for log correlation

#### Scenario: crews.json entry does not contain plaintext admiral secret after launch

- **WHEN** a crew is launched and `_finish_crew_setup` completes successfully
- **THEN** the `admiral_secret` field in the crew's `crews.json` entry is absent or contains
  only a non-reversible identifier, not the Ed25519 private key or seed that was generated

#### Scenario: crews.json entry does not contain plaintext policy_signing_key after launch

- **WHEN** a crew is launched and policy injection succeeds
- **THEN** the `policy_signing_key` field in the crew's `crews.json` entry is absent or
  contains only a non-reversible identifier, not the plaintext key

#### Scenario: Injection still works after credential hygiene

- **WHEN** the transport injects the admiral public key and policy signing key
- **THEN** both files inside the crew container are correctly written with the real values,
  confirming that hygiene of `crews.json` does not break the injection path

### Requirement: Authentication gate precedes registry write in launch
The system SHALL check for a valid auth file at the very start of `launch`, before writing any placeholder into the crew registry. If no valid auth is present, `launch` SHALL initiate the device auth flow and return the `login_url` and `code` in the error response so the caller can complete authentication and then retry `launch` without a separate API call. The crew registry SHALL NOT be modified when launch fails the auth gate.

#### Scenario: launch called before authentication
- **WHEN** `launch` is called and no valid auth file exists
- **THEN** the device auth flow is initiated automatically, the response includes `error: "not_authenticated"`, `login_url`, and `code` (or `null` if the URL could not be extracted within the timeout), no registry entry is written for the crew, and the caller can open the `login_url`, complete auth, and retry `launch` without calling `POST /login` first

#### Scenario: launch called while a login flow is already pending
- **WHEN** `launch` is called, no valid auth file exists, and a login flow is already in progress
- **THEN** the response includes `error: "not_authenticated"` and `login_pending: true` indicating the caller should poll `GET /login` before retrying

#### Scenario: launch called after completing auth
- **WHEN** `launch` is called and a valid auth file exists
- **THEN** the auth gate passes, the registry placeholder is written, and launch proceeds normally
