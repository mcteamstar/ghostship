## MODIFIED Requirements

### Requirement: Secrets delivered via stdin, not process arguments

When the transport runs a container-exec script that requires a secret value, the secret
SHALL be passed to the script via its stdin stream. The script SHALL read the secret from
`sys.stdin.read()` and strip surrounding whitespace. The secret value SHALL NOT appear in
any element of the process's argument list (`argv`). Container creation specs for crew
containers SHALL include `no_new_privileges: true` to prevent privilege escalation via
setuid binaries.

The admiral public key is the exception to the container-exec/stdin pattern: it SHALL be
delivered as a Podman secret, created via `podman secret create` and attached to the
container spec at `container_create` time (target `.admiral_public_key`, uid/gid 0, mode
0444). It SHALL NOT be passed to any container-exec script, and the private key SHALL NOT
enter the container in any form.

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
