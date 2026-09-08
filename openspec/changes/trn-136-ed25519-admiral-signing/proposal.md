## Why

The admiral signing mechanism uses HMAC with a shared secret: the transport holds the secret and injects a copy into the crew container. A compromised agent running as `kirocrew` can read and overwrite `.admiral_secret`, enabling it to forge Admiral mail that the crew accepts as legitimate. Asymmetric signing removes this attack — the crew container holds only the public key, which is useless for forgery.

## What Changes

- **Key generation**: at crew launch, generate an Ed25519 keypair instead of a random HMAC secret. Store the private key in `DATA_DIR/secrets/<crew_id>.admiral_secret` (same path, different content). Never inject the private key into the container.
- **Public key injection**: inject the Ed25519 public key (raw bytes, base64-encoded) into the container as `.admiral_public_key` instead of `.admiral_secret`. The container no longer holds any signing capability.
- **Signing**: `captain.py` signs Admiral mail with Ed25519 (via `cryptography`) instead of HMAC. The `X-Admiral-Sig` header carries the base64-encoded detached signature.
- **Verification**: `verify-admiral-sig` verifies against `.admiral_public_key` using Ed25519 instead of HMAC against `.admiral_secret`.
- **`inject_admiral_secret.py`**: rename to `inject_admiral_key.py` (or reuse the same script), updated to write the public key file instead of the HMAC secret.
- **`docs/auth.md`**: update the threat model section to describe the keypair model, what it protects against, and the residual public-key-substitution risk.

No breaking changes to the `X-Admiral-Sig` header name or the `verify-admiral-sig` exit code contract (0 = valid, 1 = mismatch, 2 = key not found).

## Capabilities

### New Capabilities
_(none)_

### Modified Capabilities
- `crew-auth`: Admiral mail signing changes from HMAC shared secret to Ed25519 asymmetric keypair; crew containers hold only the public key; the private key never leaves the transport.
- `secret-delivery-hardening`: public key injection still uses stdin delivery (same pattern as HMAC secret); the change is what is delivered, not how.

## Impact

- `transport/lifecycle.py` — keypair generation replacing `secrets.token_hex(32)`; inject public key instead of HMAC secret.
- `transport/captain.py` — `_format_captain_mail` signs with Ed25519 private key; `_read_crew_secret` reads the private key.
- `transport/registry.py` — secret path and file format unchanged (still `<crew_id>.admiral_secret`); content changes from hex string to PEM/raw private key bytes.
- `crews/_base/admission/verify-admiral-sig` — verify with Ed25519 public key from `.admiral_public_key` instead of HMAC from `.admiral_secret`.
- `transport/container_scripts/inject_admiral_secret.py` — updated (or replaced) to write the public key to `.admiral_public_key`.
- `docs/auth.md` — threat model updated.
- `tests/unit/` — update signing/verification tests.
- `cryptography` package already in `requirements.txt` (used by `pyjwt`). Ed25519 support available via `cryptography.hazmat.primitives.asymmetric.ed25519`.
