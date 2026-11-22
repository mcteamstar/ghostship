# admiral-sig/key-delivery Specification

## Purpose

Defines the delivery and isolation of Admiral signing material and its verification in crews.

## Requirements

### Requirement: Admiral signing keys are isolated

The transport SHALL generate an Ed25519 keypair before crew creation, keep the private key only at `DATA_DIR/secrets/<crew_id>.admiral_secret` with mode 0600, and never inject it. The public key SHALL be a root-owned, read-only Podman secret at `/run/secrets/.admiral_public_key` (mode 0444), outside home/workspace volumes and not written by container exec.

#### Scenario: Transport generates Ed25519 keypair at launch

- **WHEN** a crew is launched
- **THEN** an Ed25519 keypair is generated before the container is created; the private key
  is stored outside the container and the public key is injected as a read-only secret
  inside the container

#### Scenario: Compromised agent cannot forge Admiral mail by reading the public key

- **WHEN** an agent process running as `kirocrew` reads `.admiral_public_key`
- **THEN** it cannot derive the private key from the public key and therefore cannot
  produce a valid `X-Admiral-Sig` for a forged message

#### Scenario: Compromised agent cannot forge Admiral mail by substituting the public key

- **WHEN** an agent process running as `kirocrew` attempts to overwrite `.admiral_public_key`
  with a public key of its own choosing
- **THEN** the write fails, because `.admiral_public_key` is a read-only Podman secret mount
  and the container lacks `CAP_SYS_ADMIN` to remount it read-write

### Requirement: Admiral mail is signed with Ed25519

`_format_captain_mail` SHALL sign the canonical length-prefixed payload with Ed25519, reject Subject or From values containing CR/LF before signing, and SHALL NOT use the old interpolation or HMAC path.

#### Scenario: Admiral mail carries valid Ed25519 signature

- **WHEN** `captain(action="order", ...)` delivers a standing order to a crew
- **THEN** the mail includes an `X-Admiral-Sig` header containing a base64url-encoded
  Ed25519 signature over the canonical length-prefixed payload

#### Scenario: Signer rejects newline header values
- **WHEN** Subject or From contains a carriage return or newline
- **THEN** `_format_captain_mail` raises `ValueError` before producing a signature

### Requirement: Admiral signature verifier uses the public key only

`verify-admiral-sig` SHALL verify `X-Admiral-Sig` with the public key and canonical payload, SHALL NOT read `.admiral_secret`, and SHALL return 0 for valid, 1 for invalid structure/signature, or 2 when the public key is absent.

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

### Requirement: Threat model for admiral secret delivery is documented
The system's documentation SHALL describe the threat model for the admiral secret: why it must not reside in a file readable by agent processes, what privilege boundary the env-var delivery provides, and the residual risk (host-level access bypasses all container-side controls).

#### Scenario: Documentation covers admiral secret threat model
- **WHEN** a user or operator reads the security section of `docs/auth.md`
- **THEN** they find an explanation of why the admiral secret must not be in a world-readable file, what the delivery mechanism protects against, and what it does not protect against
