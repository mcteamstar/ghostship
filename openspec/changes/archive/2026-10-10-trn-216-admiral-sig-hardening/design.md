## Context

See `proposal.md — Why` for motivation. Three defects exist today:

1. **Header injection** — payload built via `f"Subject:{subject}\nFrom:{sender}\n\n{body}"`;
   a newline in `subject` or `sender` would push bytes into the wrong field.
2. **Multipart crash** — `msg.get_payload()` returns a `list` for multipart messages;
   `.rstrip('\n')` on a list raises `AttributeError` (not a clean exit 1).
3. **Strip asymmetry** — the verifier strips `\n` from body; the signer strips `\r\n`.
   A body ending in `\r` signs fine but verifies differently under the old format.

Both the signer (`transport/captain.py:_format_captain_mail`) and verifier
(`crews/_base/admission/verify-admiral-sig`) must be updated together; they share a
payload format contract. Existing tests in `tests/unit/test_admiral_sig.py` test the
current format and will need updating.

Because keypairs are ephemeral per-crew material and signer/verifier are deployed as a
unit, there is no cross-version compatibility constraint.

## Goals / Non-Goals

**Goals:**
- Eliminate all three defects with a single, coherent payload format change.
- Keep the exit-code contract (0/1/2) unchanged — Raven and other callers are not
  affected.
- Keep the key format, secret storage path, and Podman secret mount unchanged.
- All new behavior covered by unit tests; end-to-end round-trip covered by an
  integration test.

**Non-Goals:**
- Re-keying existing crews (the payload format is an implementation detail of the
  admission scripts, not a persisted format; no migration of stored signatures needed).
- Supporting simultaneous old/new payload format (not needed — signer and verifier
  are co-deployed).
- Changes to the exit-code semantics, retry logic, or public key loading path.
- Changes outside `captain.py` (`_format_captain_mail` only), `verify-admiral-sig`,
  and their tests.

## Decisions

### D1: Length-prefixed payload format over a separator-based format

**Chosen:** `{len(subject_utf8)}\n{subject_bytes}{len(from_utf8)}\n{from_bytes}{body_bytes}`

**Alternatives considered:**

- *Old format with escaping* — escape `\n` in header values before interpolation. Rejected:
  escaping logic must be identical on both sides, and a future maintainer adding a new
  header field faces the same trap again. A structural format is safer.
- *JSON envelope* — `{"subject":..., "from":..., "body":...}` then sign the JSON. Rejected:
  JSON key ordering and encoding edge cases (non-ASCII in headers, BOM) introduce new
  ambiguities; Python's `json.dumps` is not guaranteed stable across versions for all
  inputs.
- *NUL-separated fields* — `subject\x00from\x00body`. Rejected: NUL bytes are valid in
  raw binary but require care in the Python `email` library context; length prefixes are
  unambiguous with no special-character assumptions.
- *Length-prefixed with a fixed separator after each value* — adds no benefit over pure
  length-prefixing and increases implementation surface.

The chosen format requires only integer arithmetic and byte-string concatenation; it is
trivially verifiable by inspection.

### D2: No body normalization on either side

**Chosen:** use `msg.get_payload()` result verbatim (no strip, no rstrip).

The signer in `_format_captain_mail` already calls `body.rstrip("\r\n")` before deriving
the Subject from the first line and before constructing the payload. That rstrip
normalizes `body` before it enters the payload, so the `body_bytes` in the payload are
already normalized at the signer — but only by `\r\n`. The verifier was stripping only
`\n`, creating the asymmetry. The fix: remove the strip from the verifier entirely, and
in the signer, the existing `body.rstrip("\r\n")` continues to produce a normalized body
string, which is what gets length-prefixed and signed. Both sides end up operating on the
same bytes.

Rationale: the signer controls the body content (it generates it from a template); there
is no risk of meaningful trailing whitespace in Admiral orders. Removing the verifier-side
strip is safe, and symmetric with the fact that the signer has already normalized.

### D3: Header newline validation is a ValueError / exit 1, not silent clamping

**Chosen:** raise `ValueError` in the signer; exit 1 in the verifier when header values
contain `\n` or `\r`.

A newline in a Subject or From header value is either a bug in the calling code or an
attack. Silent clamping (stripping the newline) would mask the bug; hard failure forces
the caller to fix it. In the verifier, the appropriate security response to a structurally
invalid message is exit 1 (not genuine Admiral mail).

### D4: Multipart guard exits 1 (not 2)

**Chosen:** exit 1 when `get_payload()` returns a list.

Exit 2 means "cannot verify due to transient environment issue (missing key)". A multipart
message is not a transient issue; it is a definitively non-Admiral-format message. Exit 1
("not genuine") is correct.

## Risks / Trade-offs

- **Existing signed messages become unverifiable** — Any Admiral mail already in the
  captain mailbox was signed with the old format. After the update, `verify-admiral-sig`
  will exit 1 on those messages. Mitigation: old messages were already processed by Raven
  (Raven marks them cur/). Any unread old-format message will appear invalid after the
  update; this is acceptable because (a) the fleet is updated atomically per crew, and
  (b) the Admiral can resend any order that was missed during the transition window.
  → Mitigation: document in tasks.md that the crew needs a re-send of any pending orders
  after the update.

- **Test suite currently uses old payload format** — `_sign()` in `test_admiral_sig.py`
  builds the old payload. All existing `VerifyAdmiralSigTests` will fail against the new
  verifier until updated. Mitigation: the test file is entirely under our control and must
  be updated in the same PR as the script changes.

- **No version negotiation in the protocol** — A crew running the new verifier cannot
  process mail signed by an old transport instance. Mitigation: signer and verifier are
  co-deployed; the Containerfile installs both from the same image build.

## Migration Plan

1. Update `_format_captain_mail` in `transport/captain.py` to use the new payload format
   and add header validation.
2. Update `verify-admiral-sig` to use the new payload format, add multipart guard, add
   header validation, remove body strip.
3. Update `tests/unit/test_admiral_sig.py`: update `_sign()` helper to new format; add
   new test cases for the three defects.
4. Add integration test: sign with new `_format_captain_mail`, verify with
   `verify-admiral-sig`, assert exit 0.
5. Deploy atomically — transport and crew image must be rebuilt together.
6. After deployment, resend any Admiral standing orders that were in-flight during the
   transition (the Admiral can re-issue them; they are idempotent).
