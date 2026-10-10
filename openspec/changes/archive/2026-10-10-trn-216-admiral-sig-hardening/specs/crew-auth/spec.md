## MODIFIED Requirements

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
