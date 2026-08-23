## MODIFIED Requirements

### Requirement: Admiral mail signature verification is reliable
The `verify-admiral-sig` script SHALL strip trailing whitespace from the parsed mail body before computing the expected HMAC, matching how the transport signs the body before delivery.

#### Scenario: Captain order with valid signature is accepted
- **WHEN** Raven reads a captain mailbox message sent by the transport via `_format_captain_mail`
- **THEN** `verify-admiral-sig` exits 0 and Raven treats the message as a genuine Admiral standing order

#### Scenario: Captain order with invalid signature is rejected
- **WHEN** a message in the captain mailbox has a forged or missing `X-Admiral-Sig` header
- **THEN** `verify-admiral-sig` exits 1 and Raven does not act on it
