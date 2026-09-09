# Crew Auth Specification

## Purpose

Authenticate kiro-cli inside crew containers exactly once per machine, and reuse that authentication automatically for every crew created afterward, instead of requiring a fresh login per crew.

## Requirements

### Requirement: Academy auth state machine
The Ghost Academy has exactly three auth states — unauthenticated, pending, and authenticated — determined by the presence and content of `DATA_DIR/ga-kiro-auth`. Transitions are: unauthenticated → pending via `POST /login`; pending → authenticated via `GET /login` completing; authenticated → unauthenticated via `POST /logout`. No other transitions are valid.

#### Scenario: Cannot login when already authenticated
- **WHEN** `POST /login` is called and `ga-kiro-auth` exists and is non-empty
- **THEN** the transport returns HTTP 409 with a message indicating the academy is already authenticated and `POST /logout` must be called first

#### Scenario: Cannot login when login already in progress
- **WHEN** `POST /login` is called while a login flow is already pending
- **THEN** the transport returns HTTP 409 with a message indicating a login is already in progress and `GET /login` should be polled

#### Scenario: Auth injected into all running crews on login completion
- **WHEN** `GET /login` first returns `status: "complete"`
- **THEN** the transport has written `ga-kiro-auth` with mode `0600` and has injected the fresh auth rows into every crew whose registry status is `running`, without restarting those crews

#### Scenario: Auth cleared from all running crews on logout
- **WHEN** `POST /logout` is called and the academy is authenticated
- **THEN** `ga-kiro-auth` is deleted and the transport has executed `DELETE FROM auth_kv` in every running crew's kiro-cli SQLite DB

#### Scenario: Orphaned temp containers cleaned up on startup
- **WHEN** the transport starts and one or more containers named `ga-login-*` exist
- **THEN** those containers are stopped and removed during `_reconcile_registry` before any other operations

### Requirement: First-time device auth flow
The system SHALL initiate a kiro-cli device auth flow inside the crew container when no `ga-kiro-auth` file exists (or it exists but is empty), and return a login URL (and code, if available) instead of finishing crew setup.

#### Scenario: No auth file exists
- **WHEN** `launch` is called, `DATA_DIR/ga-kiro-auth` does not exist or is empty, and no currently running crew can supply auth rows as a fallback
- **THEN** the system starts `kiro-cli login --use-device-flow` (plus any configured license/identity-provider/region flags) inside the crew container, registers the crew with status `auth_required` and the returned login URL, and returns that status to the caller without minting a cookie

#### Scenario: Resuming after auth
- **WHEN** `launch` is called again with the same `crew_id` whose registry status is `auth_required`
- **THEN** the system checks the crew container's kiro-cli database for completed auth; if found, it writes the auth rows to `ga-kiro-auth` and proceeds to finish crew setup; if not found, it returns the same `auth_required` status and login URL again

### Requirement: Auth reuse across crews
The system SHALL read the saved `ga-kiro-auth` file and inject its rows into every subsequent crew's kiro-cli database, so a single login authenticates all future crews without repeating the device auth flow. `ga-kiro-auth` is a single plain file under `DATA_DIR`, mode `0600` — not a Podman secret — so reading it never involves Podman's secret API or file-driver backing store.

#### Scenario: Auth file has content
- **WHEN** `launch` creates a new crew and `DATA_DIR/ga-kiro-auth` exists with content
- **THEN** the system injects the decoded auth rows into the new crew's kiro-cli SQLite database during setup, with no login prompt shown to the caller

#### Scenario: Auth file missing or empty
- **WHEN** `DATA_DIR/ga-kiro-auth` does not exist or is empty
- **THEN** the system falls back to reading auth rows directly from any currently running crew's kiro-cli database instead

#### Scenario: Auth file is created or refreshed
- **WHEN** a completed device-auth flow creates or replaces the auth file
- **THEN** the file is written in place with mode `0600`, flushed, for later launches to read

### Requirement: Identity provider configuration

The system SHALL direct the device auth flow at a configured identity provider when `KIRO_IDENTITY_PROVIDER`/`KIRO_REGION`/`KIRO_LICENSE` are set, and SHALL fall back to Builder ID (free tier) when they are not. When falling back to Builder ID, `kiro-cli` may present an interactive login-method selection menu before the device code appears; the system SHALL answer that menu (accepting the Builder ID default) rather than treating its appearance as a failure.

When `KIRO_API_KEY` is set, the system SHALL skip the device-code auth flow entirely and inject the key as an env var into crew containers. The device-code path SHALL remain the default when `KIRO_API_KEY` is unset.

#### Scenario: Identity provider configured

- **WHEN** `KIRO_IDENTITY_PROVIDER` and `KIRO_REGION` are set on the transport container
- **THEN** the `kiro-cli login` command run during first-time auth includes `--identity-provider` and `--region` (and `--license` if `KIRO_LICENSE` is set)

#### Scenario: No identity provider configured

- **WHEN** none of `KIRO_IDENTITY_PROVIDER`, `KIRO_REGION`, `KIRO_LICENSE` are set
- **THEN** `kiro-cli login` runs with only `--use-device-flow`, authenticating against the default Builder ID identity; if kiro-cli shows a login-method selection menu first, the system answers it to select Builder ID and the flow still completes with a device code and URL

#### Scenario: KIRO_API_KEY set — device flow skipped

- **WHEN** `KIRO_API_KEY` is set in the transport environment and `launch` is called
- **THEN** the system does NOT call `_initiate_login()`, does NOT require `ga-kiro-auth` to exist, and does NOT inject `auth_b64` rows into the crew's SQLite DB
- **THEN** `KIRO_API_KEY` is passed as an env var to the crew container at creation time
- **THEN** kiro-cli inside the crew authenticates via the env var without a device-code exchange

#### Scenario: KIRO_API_KEY unset — device flow unchanged

- **WHEN** `KIRO_API_KEY` is unset
- **THEN** all existing device-code auth behaviour is unchanged — `ga-kiro-auth`, `_initiate_login()`, and `inject_auth.py` are used as before

### Requirement: Crew secrets not persisted in plaintext after injection

After the transport successfully injects the admiral public key and `policy_signing_key` into a
crew container, the registry entry written to `crews.json` SHALL NOT contain the plaintext
values of those secrets. Instead, the registry SHALL store a non-reversible identifier
derived from each secret sufficient for log correlation but useless for replay. The admiral
Ed25519 private key SHALL be stored in `DATA_DIR/secrets/<crew_id>.admiral_secret` only;
it SHALL NOT appear in `crews.json` in any form. The public key MAY be stored in the
registry for reference, but this is not required.

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

### Requirement: Admiral mail signed with Ed25519 asymmetric keypair

The transport SHALL generate an Ed25519 keypair at crew launch time, before the crew
container is created. The private key SHALL be stored in
`DATA_DIR/secrets/<crew_id>.admiral_secret` (mode 0600) and SHALL never be injected into
the crew container. The public key SHALL be delivered to the crew container as a Podman
secret, mounted read-only at `.admiral_public_key` (owned by root, mode 0444) in the same
directory as the former `.admiral_secret`. It SHALL NOT be written via a container-exec
script.

The `captain.py` signing path SHALL use the Ed25519 private key to produce a detached
signature over the same payload as before (`Subject:<s>\nFrom:<f>\n\n<body>`). The
resulting signature (raw bytes, base64url-encoded) SHALL be placed in the `X-Admiral-Sig`
header. The `hmac` signing path SHALL be removed.

The `verify-admiral-sig` script SHALL verify the `X-Admiral-Sig` header using the Ed25519
public key read from `.admiral_public_key`. It SHALL NOT read `.admiral_secret`. The exit
code contract (0 = valid, 1 = mismatch, 2 = key not found) is unchanged.

#### Scenario: Transport generates Ed25519 keypair at launch

- **WHEN** a crew is launched
- **THEN** an Ed25519 keypair is generated before the container is created; the private key
  is stored in `DATA_DIR/secrets/<crew_id>.admiral_secret`; the public key is delivered to
  the container as a read-only Podman secret mounted at `.admiral_public_key`; the private
  key never enters the container

#### Scenario: Admiral mail carries valid Ed25519 signature

- **WHEN** `captain(action="order", ...)` delivers a standing order to a crew
- **THEN** the mail includes an `X-Admiral-Sig` header containing a base64url-encoded
  Ed25519 signature over the canonical signing payload

#### Scenario: verify-admiral-sig accepts genuine Admiral mail

- **WHEN** `verify-admiral-sig` processes mail signed with the crew's Ed25519 private key
- **THEN** it reads `.admiral_public_key`, verifies the signature, and exits with code 0

#### Scenario: verify-admiral-sig rejects forged mail

- **WHEN** `verify-admiral-sig` processes mail whose `X-Admiral-Sig` does not match the
  Ed25519 public key in `.admiral_public_key`
- **THEN** it exits with code 1

#### Scenario: verify-admiral-sig exits 2 when public key file absent

- **WHEN** `verify-admiral-sig` cannot find `.admiral_public_key` after retries
- **THEN** it exits with code 2 (transient — same behaviour as before for missing secret)

#### Scenario: Compromised agent cannot forge Admiral mail by reading the public key

- **WHEN** an agent process running as `kirocrew` reads `.admiral_public_key`
- **THEN** it cannot derive the private key from the public key and therefore cannot
  produce a valid `X-Admiral-Sig` for a forged message

#### Scenario: Compromised agent cannot forge Admiral mail by substituting the public key

- **WHEN** an agent process running as `kirocrew` attempts to overwrite `.admiral_public_key`
  with a public key of its own choosing
- **THEN** the write fails, because `.admiral_public_key` is a read-only Podman secret mount
  and the container lacks `CAP_SYS_ADMIN` to remount it read-write
