# Crew Auth Specification

## Purpose

Authenticate kiro-cli inside crew containers exactly once per machine, and reuse that authentication automatically for every crew created afterward, instead of requiring a fresh login per crew.

## Requirements

### Requirement: First-time device auth flow
The system SHALL initiate a kiro-cli device auth flow inside the crew container when no `ga-kiro-auth` file exists (or it exists but is empty), and return a login URL (and code, if available) instead of finishing crew setup.

#### Scenario: No auth file exists
- **WHEN** `launch` is called, `DATA_DIR/ga-kiro-auth` does not exist or is empty, and no currently running crew can supply auth rows as a fallback
- **THEN** the system starts `kiro-cli login --use-device-flow` (plus the `--license`/identity-provider/region flags for the login method) inside the crew container, registers the crew with status `auth_required` and the returned login URL, and returns that status to the caller without minting a cookie

#### Scenario: Resuming after auth
- **WHEN** `launch` is called again with the same `crew_id` whose registry status is `auth_required`
- **THEN** the system checks the crew container's kiro-cli database for completed auth; if found, it writes the auth rows to `ga-kiro-auth` and proceeds to finish crew setup; if not found, it returns the same `auth_required` status and login URL again

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
secret, mounted read-only at `/run/secrets/.admiral_public_key` (owned by root, mode 0444).
The mount target SHALL NOT sit inside the home volume or the workspace volume.
It SHALL NOT be written via a container-exec script.

The `captain.py` signing path (`_format_captain_mail`) SHALL use the Ed25519 private key
to produce a detached signature over the canonical length-prefixed payload defined in
`admiral-sig/payload-format`. The old string-interpolation payload
(`Subject:<s>\nFrom:<f>\n\n<body>`) SHALL NOT be used. The `hmac` signing path SHALL be
removed.

Before constructing the signing payload, the signer SHALL validate that the Subject and
From header values contain no newline characters (`\n` or `\r`); if either does, it SHALL
raise `ValueError` without producing a signature.

The `verify-admiral-sig` script SHALL verify the `X-Admiral-Sig` header using the Ed25519
public key read from `.admiral_public_key`, constructing the payload using the same
canonical length-prefixed encoding. It SHALL NOT read `.admiral_secret`. The exit code
contract (0 = valid, 1 = mismatch or invalid message structure, 2 = key not found) is
unchanged.

#### Scenario: Transport generates Ed25519 keypair at launch

- **WHEN** a crew is launched
- **THEN** an Ed25519 keypair is generated before the container is created; the private key
  is stored outside the container and the public key is injected as a read-only secret
  inside the container

#### Scenario: Admiral mail carries valid Ed25519 signature

- **WHEN** `captain(action="order", ...)` delivers a standing order to a crew
- **THEN** the mail includes an `X-Admiral-Sig` header containing a base64url-encoded
  Ed25519 signature over the canonical length-prefixed payload

#### Scenario: verify-admiral-sig accepts genuine Admiral mail

- **WHEN** `verify-admiral-sig` processes mail signed with the crew's Ed25519 private key
  using the canonical length-prefixed payload
- **THEN** it reads `.admiral_public_key`, verifies the signature, and exits with code 0

#### Scenario: verify-admiral-sig rejects forged mail

- **WHEN** `verify-admiral-sig` processes mail whose `X-Admiral-Sig` does not match the
  Ed25519 public key in `.admiral_public_key`
- **THEN** it exits with code 1

#### Scenario: verify-admiral-sig exits 2 when public key file absent

- **WHEN** `verify-admiral-sig` cannot find `.admiral_public_key` after retries
- **THEN** it exits with code 2 (transient)

#### Scenario: Compromised agent cannot forge Admiral mail by reading the public key

- **WHEN** an agent process running as `kirocrew` reads `.admiral_public_key`
- **THEN** it cannot derive the private key from the public key and therefore cannot
  produce a valid `X-Admiral-Sig` for a forged message

#### Scenario: Compromised agent cannot forge Admiral mail by substituting the public key

- **WHEN** an agent process running as `kirocrew` attempts to overwrite `.admiral_public_key`
  with a public key of its own choosing
- **THEN** the write fails, because `.admiral_public_key` is a read-only Podman secret mount
  and the container lacks `CAP_SYS_ADMIN` to remount it read-write

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
