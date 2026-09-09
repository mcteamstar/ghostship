## MODIFIED Requirements

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

## ADDED Requirements

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
