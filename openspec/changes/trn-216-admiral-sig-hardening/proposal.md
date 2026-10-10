## Why

The `verify-admiral-sig` admission script and its signing counterpart in
`transport/captain.py` contain three defects that allow malformed or adversarial
messages to bypass signature verification or crash the verifier outright. Left
unfixed, a crew agent could be manipulated into treating unsigned or forged mail as
genuine Admiral standing orders.

## What Changes

- **Fix header injection**: the signing payload `Subject:<s>\nFrom:<f>\n\n<body>` is
  constructed by simple string interpolation. A Subject or From value containing a
  literal `\n` would inject extra lines into the payload, breaking the signer/verifier
  boundary and potentially allowing an attacker to craft a message that verifies as
  a different body. Both signer and verifier must validate that header values contain
  no newlines before constructing the payload.

- **Fix multipart crash**: `msg.get_payload()` returns a `list` for MIME multipart
  messages; calling `.rstrip('\n')` on a list raises `AttributeError`, crashing the
  verifier with an unhandled exception (which is not exit 1 — it is a Python traceback
  to stderr and a non-zero exit, but not a clean security exit). The verifier must
  guard against this case. Multipart messages are not legitimate Admiral mail; they
  should cleanly exit 1.

- **Fix body whitespace stripping**: the verifier calls `.rstrip('\n')` on the body
  before constructing the signed payload, but the signer calls `body.rstrip("\r\n")`
  before signing. These strip different characters (`\r` is stripped only by the
  signer), meaning a body ending in `\r` will verify successfully (signer stripped it)
  but a body constructed with trailing `\r` only in the verifier path would fail.
  More critically, the strip is asymmetric with the email library's behavior: if a
  message body contains meaningful trailing whitespace (rare but valid), the strip
  creates a silent ambiguity. The fix is a **length-prefixed payload format** that
  encodes the exact body bytes without normalization, removing the strip entirely from
  both sides.

- **BREAKING**: the payload format changes. New signatures are not verifiable by the
  old verifier and vice versa. The transition strategy is a clean break: transport
  issues new-format signatures from the next release; the verifier accepts only
  new-format signatures. Because the signing secret and public key are per-crew
  ephemeral material, no cross-version interoperability is needed — all components
  in a given crew container are deployed together.

## Capabilities

### New Capabilities

- `admiral-sig/payload-format`: Defines the canonical payload encoding for Ed25519
  Admiral mail signatures — length-prefixed, no normalization, with validated header
  values. Both signer (`transport/captain.py`) and verifier
  (`crews/_base/admission/verify-admiral-sig`) must conform to this spec.

### Modified Capabilities

- `crew-governance`: The security model for Admiral mail authentication is part of
  governance. The requirement that signed Admiral mail is unforgeable depends on the
  correctness of the payload construction. The spec must reflect the hardened payload
  format and the header-injection guard as requirements.

## Impact

- `crews/_base/admission/verify-admiral-sig` — verifier rewrite (payload construction,
  `get_payload()` guard, header validation).
- `transport/captain.py` — `_format_captain_mail` signing path (payload construction,
  header validation).
- `tests/unit/test_admiral_sig.py` — new test cases for each defect; existing tests
  may need updating for the new payload format.
- New integration test: sign with the new signer, verify with the new verifier end-to-end.
- No database, no API surface, no external dependencies added.
