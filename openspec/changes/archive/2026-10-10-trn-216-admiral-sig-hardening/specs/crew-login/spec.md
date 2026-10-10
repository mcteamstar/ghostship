## MODIFIED Requirements

### Requirement: Admiral mail signature verification is reliable

The `verify-admiral-sig` script SHALL construct the verification payload using the
canonical length-prefixed encoding defined in `admiral-sig/payload-format`. It SHALL NOT
strip, normalize, or otherwise modify the body before payload construction. It SHALL
exit 1 cleanly when the message is multipart (i.e., `get_payload()` returns a non-string
value) rather than raising an unhandled exception.

#### Scenario: Captain order with valid signature is accepted

- **WHEN** Raven reads a captain mailbox message sent by the transport via `_format_captain_mail`
- **THEN** `verify-admiral-sig` exits 0 and Raven treats the message as a genuine Admiral
  standing order

#### Scenario: Captain order with invalid signature is rejected

- **WHEN** a message in the captain mailbox has a forged or missing `X-Admiral-Sig` header
- **THEN** `verify-admiral-sig` exits 1 and Raven does not act on it

#### Scenario: Multipart message is rejected cleanly

- **WHEN** `verify-admiral-sig` processes a MIME multipart message
- **THEN** it exits 1 without raising an unhandled exception
