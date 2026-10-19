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

### Requirement: Credential injection uses container_archive_put, not shell exec
The transport SHALL deliver credential files into crew containers via `container_archive_put` (atomic tar write) rather than `sh -c` shell exec. This applies to: Claude OAuth credential injection (`_inject_claude_auth`), Codex credential injection (`_inject_codex_auth`), and dashboard cookie injection (`_write_dashboard_cookie`). No credential injection path SHALL use `sh -c`, `python3 -c`, or any other inline shell or interpreter exec to write credential content.

#### Scenario: Claude auth injection does not use shell exec
- **WHEN** `_inject_claude_auth` is called to deliver credentials into a crew container
- **THEN** the credentials are written via `container_archive_put` as a tar member; no `sh -c` or `printf` subprocess is spawned

#### Scenario: Dashboard cookie injection does not use inline python exec
- **WHEN** `_write_dashboard_cookie` is called to write the cookie into a crew container
- **THEN** the cookie value is written via `container_archive_put`; no `python3 -c` subprocess is spawned

### Requirement: inject_policy.py uses stdin for HMAC key delivery

`inject_policy.py` SHALL read the HMAC policy signing key from `sys.stdin`
(via `sys.stdin.read().strip()`), not from `sys.argv`. The caller in
`lifecycle.py` SHALL deliver the key via the `input` parameter of
`container_exec_stdin`, closing the write end after the key is written. The key
SHALL NOT appear in any element of `argv` of the `inject_policy.py` process.

#### Scenario: inject_policy.py signing key not in argv

- **WHEN** `_inject_policy` is called to sign and write crew policy files
- **THEN** the HMAC policy signing key does not appear in any positional argument
  passed to the `inject_policy.py` process; it is delivered exclusively via stdin

#### Scenario: inject_policy.py signing key delivered via stdin

- **WHEN** `_inject_policy` calls `container_exec_stdin` to run `inject_policy.py`
- **THEN** the base64-encoded JSON payload containing `policy_signing_key` is written
  to the process's stdin stream; the process reads it with `sys.stdin.read().strip()`

### Requirement: Config repr masks sensitive credential fields
The `Config` dataclass SHALL hold no backend credential fields; backend credentials live only in the credential store. The credential store and its records SHALL override `__repr__` so that no credential value appears in `repr()` or `str()`. Any log call that includes `repr(cfg)`, `str(cfg)` or a credential record SHALL NOT emit live credential values.

#### Scenario: Config repr does not expose API keys
- **WHEN** `repr(cfg)` is called, or `repr()` is called on a stored credential record
- **THEN** the returned string contains no credential value; credential records show `***` in place of the value
