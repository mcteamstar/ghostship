# admiral-sig/payload-format Specification

## Purpose
Defines the canonical payload encoding used to produce and verify the Ed25519
`X-Admiral-Sig` header on Admiral standing orders. Both the transport signer and
the in-container verifier MUST use exactly this encoding; divergence between the two
makes genuine orders unverifiable.

## Requirements

### Requirement: Admiral signature payload is length-prefixed and normalization-free

The signing payload for `X-Admiral-Sig` SHALL be constructed using a length-prefixed
encoding rather than direct string interpolation, to eliminate header-injection
opportunities and body-normalization ambiguity.

The canonical payload encoding is:

```
<subject-length-decimal>\n<subject-bytes><from-length-decimal>\n<from-bytes><body-bytes>
```

where:
- `<subject-length-decimal>` is the byte length of the Subject header value (UTF-8 encoded)
  as a decimal ASCII integer followed by a newline.
- `<subject-bytes>` are the exact UTF-8 bytes of the Subject header value with no
  trailing separator.
- `<from-length-decimal>` is the byte length of the From header value (UTF-8 encoded)
  as a decimal ASCII integer followed by a newline.
- `<from-bytes>` are the exact UTF-8 bytes of the From header value with no trailing
  separator.
- `<body-bytes>` are the exact UTF-8 bytes of the message body as returned by the
  Python `email` library's `get_payload()` for a simple (non-multipart) message, with
  no stripping, normalization, or modification.

The private key signs `payload_bytes`, where:

```
payload_bytes = (
    f"{len(subject_utf8)}\n".encode() + subject_utf8 +
    f"{len(from_utf8)}\n".encode() + from_utf8 +
    body_bytes
)
```

All lengths are in bytes (UTF-8), not Unicode code points.

#### Scenario: Signer and verifier construct identical payloads for a simple message

- **WHEN** the transport signs a standing order with a given Subject, From, and body
- **THEN** the verifier constructs the same payload bytes from the received message and
  the Ed25519 signature verification succeeds (exit 0)

#### Scenario: Header injection attempt does not produce a verifiable forgery

- **WHEN** an attacker constructs a message whose Subject header value contains a
  literal newline character (e.g. `Subject: real\nFrom: injected`)
- **THEN** the verifier encodes the Subject length prefix before the newline, so the
  injected bytes land inside the length-delimited subject field and are not interpreted
  as a From field; the resulting payload does not match a legitimately signed payload
  and verification exits 1

#### Scenario: Body with trailing whitespace verifies correctly

- **WHEN** the transport signs a body ending in spaces or tabs
- **THEN** the verifier uses the body bytes verbatim (no stripping) and signature
  verification exits 0, because signer and verifier both operate on the same bytes

### Requirement: Verifier rejects multipart messages before attempting signature verification

The `verify-admiral-sig` verifier SHALL exit 1 without attempting signature
verification when `msg.get_payload()` returns a non-string value (i.e., the message
is MIME multipart). Legitimate Admiral standing orders are simple plain-text messages
and SHALL NOT be multipart.

#### Scenario: Multipart message exits 1 cleanly

- **WHEN** `verify-admiral-sig` processes a MIME multipart message that carries an
  `X-Admiral-Sig` header
- **THEN** it exits 1 without raising an unhandled exception

#### Scenario: Simple plain-text message proceeds to signature check

- **WHEN** `verify-admiral-sig` processes a plain-text (non-multipart) message
- **THEN** it extracts the body as a string and proceeds to payload construction and
  signature verification

### Requirement: Signer and verifier validate header values before payload construction

Both the transport signing path and the `verify-admiral-sig` verifier SHALL reject
messages where the Subject or From header value contains a newline character (`\n` or
`\r`). The signer SHALL raise an exception; the verifier SHALL exit 1.

#### Scenario: Signer raises on newline in Subject

- **WHEN** `_format_captain_mail` is called with a body whose first line (used as
  Subject) contains a `\n` or `\r` character
- **THEN** the function raises `ValueError` before any signature is produced

#### Scenario: Verifier exits 1 on newline in Subject header value

- **WHEN** `verify-admiral-sig` parses a message and the decoded Subject header value
  contains a `\n` or `\r` character
- **THEN** it exits 1 without attempting signature construction or verification

#### Scenario: Verifier exits 1 on newline in From header value

- **WHEN** `verify-admiral-sig` parses a message and the decoded From header value
  contains a `\n` or `\r` character
- **THEN** it exits 1 without attempting signature construction or verification
