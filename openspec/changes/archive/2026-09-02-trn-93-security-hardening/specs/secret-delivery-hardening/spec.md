## Purpose

Ensures that live secret values (admiral secrets, policy signing keys, and similar one-time
credentials) are never exposed in process argument lists or `/proc/<pid>/cmdline` during
container-exec operations; secrets must be delivered via stdin only.

## ADDED Requirements

### Requirement: Secrets delivered via stdin, not process arguments
When the transport runs a container-exec script that requires a secret value, the secret
SHALL be passed to the script via its stdin stream. The script SHALL read the secret from
`sys.stdin.read()` and strip surrounding whitespace. The secret value SHALL NOT appear in
any element of the process's argument list (`argv`). Container creation specs for crew
containers SHALL include `no_new_privileges: true` to prevent privilege escalation via
setuid binaries.

#### Scenario: Secret not present in exec command arguments
- **WHEN** the transport calls `container_exec` to run `inject_admiral_secret.py` with the
  `admiral_secret` value
- **THEN** the secret value does not appear in any positional argument of the command list
  passed to Podman's exec API

#### Scenario: Script reads secret from stdin
- **WHEN** `inject_admiral_secret.py` is invoked with only the destination path as an argument
- **THEN** the script reads the secret value from stdin (stripped of whitespace) and writes
  it to the destination file with mode 0600

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
