## MODIFIED Requirements

### Requirement: Secrets delivered via stdin, not process arguments

When the transport runs a container-exec script that requires a secret value, the secret
SHALL be passed to the script via its stdin stream. The script SHALL read the secret from
`sys.stdin.read()` and strip surrounding whitespace. The secret value SHALL NOT appear in
any element of the process's argument list (`argv`). Container creation specs for crew
containers SHALL include `no_new_privileges: true` to prevent privilege escalation via
setuid binaries.

For the admiral key injection specifically: the Ed25519 public key (raw bytes) SHALL be
delivered via stdin to `inject_admiral_key.py` (or the renamed equivalent of
`inject_admiral_secret.py`), written to `.admiral_public_key` (mode 0600). The private key
SHALL NOT be passed to any container-exec script and SHALL NOT enter the container in any
form.

#### Scenario: Secret not present in exec command arguments

- **WHEN** the transport calls `container_exec` to run `inject_admiral_key.py` with the
  admiral public key
- **THEN** the public key bytes do not appear in any positional argument of the command list
  passed to Podman's exec API

#### Scenario: Script reads public key from stdin

- **WHEN** `inject_admiral_key.py` is invoked with only the destination path as an argument
- **THEN** the script reads the public key bytes from stdin and writes them to `.admiral_public_key`
  with mode 0600

#### Scenario: Script reads secret from stdin

- **WHEN** any inject script (including `inject_admiral_key.py`) is invoked with only the
  destination path as an argument
- **THEN** the script reads its secret or key material from stdin (stripped of whitespace)
  and writes it to the destination file with mode 0600; the value never appears in argv

#### Scenario: Container exec spec includes no_new_privileges

- **WHEN** a crew container is created via `container_create`
- **THEN** the Podman container spec includes `no_new_privileges: true`

#### Scenario: Worker container exec spec includes no_new_privileges

- **WHEN** a worker container is created via `worker_run`
- **THEN** the Podman container spec includes `no_new_privileges: true`
