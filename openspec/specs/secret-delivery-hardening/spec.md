# Secret Delivery Hardening Specification

## Purpose

Ensures that live secret values (admiral secrets, policy signing keys, and similar one-time
credentials) are never exposed in process argument lists or `/proc/<pid>/cmdline` during
container-exec operations; secrets must be delivered via stdin only.

## Requirements

### Requirement: Secrets delivered via stdin, not process arguments

When the transport runs a container-exec script that requires a secret value, the secret
SHALL be passed to the script via its stdin stream. The script SHALL read the secret from
`sys.stdin.read()` and strip surrounding whitespace. The secret value SHALL NOT appear in
any element of the process's argument list (`argv`). Container creation specs for crew
containers SHALL include `no_new_privileges: true` to prevent privilege escalation via
setuid binaries.

The admiral public key is the exception to the container-exec/stdin pattern: it SHALL be
delivered as a Podman secret, created via `podman secret create` and attached to the
container spec at `container_create` time (target `/run/secrets/.admiral_public_key`,
uid/gid 0, mode 0444). The target SHALL lie outside every volume mount point, so that the
directories Podman creates for it cannot render a volume-backed path unwritable to
`kirocrew`. It SHALL NOT be passed to any container-exec script, and the private key SHALL
NOT enter the container in any form.

#### Scenario: Secret not present in exec command arguments

- **WHEN** the transport calls `container_exec` to run a container-exec injection script
  (e.g. for `policy_signing_key`)
- **THEN** the secret bytes do not appear in any positional argument of the command list
  passed to Podman's exec API

#### Scenario: Script reads secret from stdin

- **WHEN** any inject script is invoked with only the destination path as an argument
- **THEN** the script reads its secret or key material from stdin (stripped of whitespace)
  and writes it to the destination file with mode 0600; the value never appears in argv

#### Scenario: Admiral public key delivered as a Podman secret, not via exec

- **WHEN** a crew container is created
- **THEN** the Ed25519 public key is attached as a Podman secret in the `container_create`
  spec, mounted read-only at `.admiral_public_key`; no `container_exec` call writes this file

#### Scenario: Admiral public key mount is read-only

- **WHEN** a process running as `kirocrew` inside the container attempts to write to
  `.admiral_public_key`
- **THEN** the write fails because the file is a read-only Podman secret mount

#### Scenario: Container exec spec includes no_new_privileges

- **WHEN** a crew container is created via `container_create`
- **THEN** the Podman container spec includes `no_new_privileges: true`

#### Scenario: Worker container exec spec includes no_new_privileges

- **WHEN** a worker container is created via `worker_run`
- **THEN** the Podman container spec includes `no_new_privileges: true`

### Requirement: Minimal capability set for crew containers
Crew containers SHALL be created with a capability drop-list that removes
`CAP_NET_RAW` and `CAP_SYS_ADMIN` from the container's effective capability set.
These capabilities are not required by the crew's workloads and reduce the blast
radius if a container is compromised.

#### Scenario: CAP_NET_RAW dropped from crew container
- **WHEN** a crew container is created
- **THEN** the Podman container spec includes `cap_drop: ["CAP_NET_RAW", "CAP_SYS_ADMIN"]`

#### Scenario: Worker container also receives capability drop
- **WHEN** a worker container is created for a single-command operation
- **THEN** the Podman container spec includes `cap_drop: ["CAP_NET_RAW", "CAP_SYS_ADMIN"]`

### Requirement: Gateway token TTL validated at startup
The `KC_GATEWAY_TOKEN_TTL` configuration value SHALL be validated at startup. A valid
value is a positive integer followed by a recognised time unit suffix (`s`, `m`, `h`, `d`).
If the value does not match, the transport SHALL log a `WARNING` naming the variable and
the offending value, and SHALL fall back to the default of `24h`. The gateway is never
started with a malformed TTL string.

#### Scenario: Well-formed TTL is accepted
- **WHEN** `KC_GATEWAY_TOKEN_TTL` is set to a value such as `12h` or `3600s`
- **THEN** the value is used without modification or warning

#### Scenario: Malformed TTL falls back to default
- **WHEN** `KC_GATEWAY_TOKEN_TTL` is set to a value such as `banana` or `0h` (zero)
- **THEN** the transport logs a `WARNING` naming `KC_GATEWAY_TOKEN_TTL` and falls back
  to `24h`; no error is raised and the transport continues starting up normally

### Requirement: Model API keys are delivered as Podman secrets, not env vars
`ANTHROPIC_API_KEY` and `OPENAI_API_KEY` SHALL be delivered to `ga-transport` via Podman secrets (`ga-crew-anthropic-api-key` and `ga-crew-openai-api-key`) mounted at `/run/secrets/`. They SHALL NOT appear as plaintext in the `environment:` block of `compose.yml`. The transport SHALL read them from the secret files at startup.

#### Scenario: Anthropic key delivered via Podman secret
- **GIVEN** `ANTHROPIC_API_KEY` is set in `ghostship.conf`
- **WHEN** `install.sh` runs
- **THEN** the Podman secret `ga-crew-anthropic-api-key` exists, `compose.yml` lists it under `ga-transport`'s `secrets:`, and `ANTHROPIC_API_KEY` is absent from the `environment:` block

#### Scenario: Anthropic key absent — no dangling secret reference
- **GIVEN** `ANTHROPIC_API_KEY` is not set
- **WHEN** `install.sh` runs
- **THEN** `compose.yml` does not reference `ga-crew-anthropic-api-key` in either the service `secrets:` list or the top-level `secrets:` block

#### Scenario: OpenAI key delivered via Podman secret
- **GIVEN** `OPENAI_API_KEY` is set in `ghostship.conf`
- **WHEN** `install.sh` runs
- **THEN** the Podman secret `ga-crew-openai-api-key` exists and `compose.yml` lists it under `ga-transport`'s `secrets:`

#### Scenario: Transport reads Anthropic key from secret file
- **GIVEN** `/run/secrets/ga-crew-anthropic-api-key` is present inside the `ga-transport` container
- **WHEN** the transport starts
- **THEN** the Anthropic API key used for crew containers is the value from the secret file

### Requirement: KIRO_API_KEY is delivered as a Podman secret
`KIRO_API_KEY` SHALL be delivered to `ga-transport` via Podman secret `ga-kiro-api-key` mounted at `/run/secrets/ga-kiro-api-key`. It SHALL NOT appear as a plaintext environment variable in `compose.yml`. The transport SHALL read it from the secret file at startup and use it to authenticate kiro-cli in crew containers (headless / Pro+ API-key path). When the secret is absent, the transport SHALL fall back to the device-code auth flow unchanged.

#### Scenario: KIRO_API_KEY delivered via Podman secret
- **GIVEN** `KIRO_API_KEY` is set in `ghostship.conf`
- **WHEN** `install.sh` runs
- **THEN** the Podman secret `ga-kiro-api-key` exists, `compose.yml` lists it under `ga-transport`'s `secrets:`, and `KIRO_API_KEY` does not appear in the `environment:` block

#### Scenario: KIRO_API_KEY absent — device-code fallback unchanged
- **GIVEN** `KIRO_API_KEY` is not set
- **WHEN** `install.sh` runs and `ga-transport` starts
- **THEN** `compose.yml` does not reference `ga-kiro-api-key` and the transport uses the device-code auth flow

#### Scenario: Transport reads kiro key from secret file
- **GIVEN** `/run/secrets/ga-kiro-api-key` is present inside `ga-transport`
- **WHEN** the transport starts
- **THEN** `KIRO_API_KEY` injected into crew containers is the value from the secret file, and the device-code flow is skipped

### Requirement: Claude OAuth token is delivered as a Podman secret
`CLAUDE_CODE_OAUTH_TOKEN` SHALL be delivered to `ga-transport` via Podman secret `ga-claude-code-oauth-token` mounted at `/run/secrets/ga-claude-code-oauth-token`. It SHALL NOT appear as plaintext in the `environment:` block of `compose.yml`. The transport SHALL read it from the secret file at startup.

#### Scenario: Claude OAuth token delivered via Podman secret
- **GIVEN** `CLAUDE_CODE_OAUTH_TOKEN` is set in `ghostship.conf`
- **WHEN** `install.sh` runs
- **THEN** the Podman secret `ga-claude-code-oauth-token` exists, `compose.yml` lists it under `ga-transport`'s `secrets:`, and `CLAUDE_CODE_OAUTH_TOKEN` is absent from the `environment:` block

#### Scenario: Claude OAuth token absent, no dangling secret reference
- **GIVEN** `CLAUDE_CODE_OAUTH_TOKEN` is not set
- **WHEN** `install.sh` runs
- **THEN** no `ga-claude-code-oauth-token` secret exists and `compose.yml` does not reference it in either the service `secrets:` list or the top-level `secrets:` block

#### Scenario: Operator's shell token not picked up
- **GIVEN** `CLAUDE_CODE_OAUTH_TOKEN` is exported in the shell that runs `install.sh` and is not set in `ghostship.conf`
- **WHEN** `install.sh` runs
- **THEN** no `ga-claude-code-oauth-token` secret is created and `compose.yml` does not reference it

#### Scenario: Token rotated on reinstall
- **GIVEN** `ga-claude-code-oauth-token` exists from a previous install and `CLAUDE_CODE_OAUTH_TOKEN` now holds a new value
- **WHEN** `install.sh` runs
- **THEN** the secret holds the new value and the transport uses it for crews launched afterwards

#### Scenario: Transport reads the token from the secret file
- **GIVEN** `/run/secrets/ga-claude-code-oauth-token` is present inside `ga-transport`
- **WHEN** the transport starts
- **THEN** the token injected into Claude-backend crews is the value from the secret file

### Requirement: Credential injection uses container_archive_put, not shell exec
The transport SHALL deliver credential files into crew containers via `container_archive_put` (atomic tar write) rather than `sh -c` shell exec. This applies to: Claude OAuth credential injection (`_inject_claude_auth`), Codex credential injection (`_inject_codex_auth`), and dashboard cookie injection (`_write_dashboard_cookie`). No credential injection path SHALL use `sh -c`, `python3 -c`, or any other inline shell or interpreter exec to write credential content.

#### Scenario: Claude auth injection does not use shell exec
- **WHEN** `_inject_claude_auth` is called to deliver credentials into a crew container
- **THEN** the credentials are written via `container_archive_put` as a tar member; no `sh -c` or `printf` subprocess is spawned

#### Scenario: Dashboard cookie injection does not use inline python exec
- **WHEN** `_write_dashboard_cookie` is called to write the cookie into a crew container
- **THEN** the cookie value is written via `container_archive_put`; no `python3 -c` subprocess is spawned

### Requirement: Config repr masks sensitive credential fields
The `Config` dataclass SHALL override `__repr__` to replace the values of sensitive fields with `***`. Sensitive fields include: `kiro_api_key`, `anthropic_api_key`, `openai_api_key`, `claude_code_oauth_token`. Any log call that includes `repr(cfg)` or `str(cfg)` SHALL NOT emit live credential values.

#### Scenario: Config repr does not expose API keys
- **WHEN** `repr(cfg)` is called on a populated `Config` instance
- **THEN** the returned string contains `***` in place of any non-empty credential field value
