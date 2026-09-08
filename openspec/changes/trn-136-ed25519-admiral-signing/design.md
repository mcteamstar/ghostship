## Context

See proposal.md for motivation.

Current state:
- `lifecycle.py` generates `secrets.token_hex(32)` as `admiral_secret`
- `inject_admiral_secret.py` writes it to `.admiral_secret` (mode 0600) in the container
- `captain.py` signs with `hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()`; the `X-Admiral-Sig` header carries the hex HMAC
- `verify-admiral-sig` reads `.admiral_secret`, recomputes the HMAC, compares with `hmac.compare_digest`
- The private key is stored at `DATA_DIR/secrets/<crew_id>.admiral_secret` (written by `registry._write_crew_secret`)
- `cryptography` is already in `requirements.txt` via `pyjwt[crypto]`

Ed25519 in Python via `cryptography`:
```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
private_key = Ed25519PrivateKey.generate()
public_key = private_key.public_key()
# Serialise private key (for storage):
private_bytes = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
# Serialise public key (for injection):
public_bytes = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
# Sign:
sig = private_key.sign(payload)  # returns 64-byte signature
# Verify (inside container, pure stdlib + cryptography):
public_key.verify(sig, payload)  # raises InvalidSignature on failure
```

The container image (`spec-ops`) already has Python 3 and the `cryptography` package available (it's installed in the transport container and available inside the crew via the crew's Python environment). Need to confirm `cryptography` is importable inside the crew container — if not, use a pure-stdlib alternative (e.g. `PyNaCl` or a bundled verifier). Most likely it's available since the spec-ops image includes Node.js and Python.

## Goals / Non-Goals

**Goals:**
- Private key never enters the container, ever.
- `X-Admiral-Sig` header format changes minimally — same header name, value changes from hex HMAC to base64url-encoded Ed25519 signature.
- Exit code contract of `verify-admiral-sig` unchanged (0/1/2).
- Existing crews break on upgrade (intentional — the `.admiral_secret` file they hold is no longer valid; they need re-injection of the public key on next restart).

**Non-Goals:**
- Replay protection — out of scope for this change (acknowledged residual risk in TRN-136).
- Immutability of `.admiral_public_key` inside the container (acknowledged residual public-key-substitution risk).
- Migrating existing running crews in-place — not needed; crews are restarted on transport upgrade and re-injection happens via `_reconcile_registry`.

## Decisions

### Decision: Raw bytes for key storage and wire format

Store private key as raw 32-byte Ed25519 seed bytes (hex-encoded for the file, same as the current HMAC secret format). Store public key as raw 32-byte bytes (base64url-encoded for the wire `X-Admiral-Sig` value). This avoids PEM overhead and matches the simplicity of the current hex approach.

`DATA_DIR/secrets/<crew_id>.admiral_secret` changes from a 64-char hex HMAC secret to a 64-char hex representation of the 32-byte Ed25519 private seed. Same file, same path, same format discipline — just different cryptographic content. Reading code that does `hex.decode()` stays compatible.

### Decision: Signature encoding in X-Admiral-Sig

Current: `X-Admiral-Sig: <64-char hex HMAC>`
New: `X-Admiral-Sig: <88-char base64url Ed25519 signature>`

The header name is unchanged. The value format changes. Any tool that parses the header must update its parser — there are exactly two: `captain.py` (producer) and `verify-admiral-sig` (consumer). Both are in this change.

**Alternative considered**: keep hex encoding for the signature. Rejected — Ed25519 signatures are 64 bytes; hex would be 128 chars vs 88 chars base64url. Base64url is standard for this use case.

### Decision: inject_admiral_key.py replaces inject_admiral_secret.py

Rename (or replace in-place) the injection script. The new script accepts the 32-byte public key via stdin (same pattern), writes it to `.admiral_public_key` instead of `.admiral_secret`. The old `.admiral_secret` file is no longer written to or read from inside the container.

### Decision: verify-admiral-sig is pure Python, no new deps

The crew container has Python 3. `cryptography` is the same package already used by the transport — confirm it's present in the crew image; if not, bundle a minimal Ed25519 verify implementation using `hashlib` + a vendored `ed25519` module, or add `cryptography` to the crew image. Most likely it's already there via the KiroCrew gateway's own Python dependencies.

### Decision: Upgrade path for existing crews

On transport restart, `_reconcile_registry` re-injects the public key for all stopped crews during the stopped→running restart sequence. Any crew that was running at the time of the transport upgrade will use the old `.admiral_secret` until it next restarts. This is acceptable — the upgrade creates a short window where old-format crews reject new-format Admiral mail with exit code 1 (signature mismatch). The Raven hold-on-exit-2 logic will not fire (that's for missing key, not mismatch), but `sdd.md` instructs Raven to escalate to Admiral on repeated failures, so the operator will be notified. For production, nuking and relaunching affected crews eliminates the window.

## Risks / Trade-offs

**`cryptography` not available in crew container** → Mitigation: check during implementation; add to spec-ops Containerfile if absent. Fallback: vendor a pure-Python ed25519 verifier (~100 lines) into `verify-admiral-sig`.

**Existing crews break on upgrade** → Documented above. Acceptable for a security change; the fix is to restart or nuke affected crews.

**`verify-admiral-sig` exit 1 (mismatch) not handled gracefully in orders** → Raven's current instructions treat exit 2 as transient (hold) but exit 1 as a hard rejection. After this change, a crew running the old HMAC verifier against a new Ed25519 signature will exit 1 and Raven will escalate. This is correct behaviour — it surfaces the upgrade mismatch clearly rather than silently retrying.

## Migration Plan

1. Deploy new transport image (rebuilds via `install.sh` as usual — source hash changes).
2. `_reconcile_registry` on startup re-injects the public key for all stopped crews.
3. Running crews hold the old `.admiral_secret` until next restart/nuke. Nuke and relaunch to immediately migrate a running crew.
4. No config changes needed.
