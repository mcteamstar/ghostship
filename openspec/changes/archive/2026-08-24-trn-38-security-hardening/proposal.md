# Proposal: trn-38-security-hardening

## Why

A Banshee security review of the transport layer surfaced nine concrete vulnerabilities — ranging from exploitable HMAC weaknesses and an unsigned upload mode flag, to plaintext admiral credentials accessible by any container process, to an open-LAN network binding with no auth. These issues collectively allow forgery, credential theft, and unauthenticated access. All are straightforward to fix with targeted, surgical changes.

## What Changes

- **HMAC token length extended from 64 to 128 bits** (`[:16]` → `[:32]`): raises brute-force bar from 2^64 to 2^128.
- **Upload mode included in evac/supply HMAC payload**: `unpack` and `bundle` flags become part of the signed token in `_sign_upload_url`, so a token cannot be replayed with a different extraction mode. `_verify_file_token` updated to check mode field on upload paths.
- **`admiral_secret` removed from plaintext `admission_policy.json`**: migrate delivery to the gateway environment (env var or Podman secret), preventing any agent process inside the crew container from reading and forging Admiral orders.
- **Default `HOST` changed from `0.0.0.0` to `127.0.0.1`**: transport no longer listens on all interfaces by default; operators opt in to LAN/external exposure via explicit config.
- **`crew_id` format validated in `_handle_file_get` and `_handle_file_put`**: adds the same regex guard already present in `launch()`, rejecting malformed IDs before path construction.
- **Empty `path` rejected with 400 in evac**: prevents signing a URL that resolves to the workspace root and streams the entire workspace.
- **`dangerously_skip_permissions=True` annotated with threat model comment**: makes the security implications of this flag self-documenting for future maintainers.
- **`crews.json` written with explicit `0o600` mode**: `_save_registry` gains `os.chmod` after write to ensure the file is not world-readable.

## Capabilities

### New Capabilities

_(none — all changes are hardening existing behaviour)_

### Modified Capabilities

- `file-transfer`: Upload HMAC payload now includes `mode` (unpack/bundle flags); `_verify_file_token` enforces mode match on upload. Empty `path` rejected with 400 in evac. HMAC length extended to 128 bits.
- `crew-lifecycle`: `admiral_secret` no longer stored plaintext in `admission_policy.json`; delivery moves to gateway environment. Documents threat model for this field.
- `mcp-server`: Default `HOST` binding changed from `0.0.0.0` to `127.0.0.1`.

## Impact

- `transport/server.py` — `_sign_upload_url`, `_verify_file_token`, `_handle_file_get`, `_handle_file_put`, `_save_registry`, `dangerously_skip_permissions` call site, `HOST` default, evac path guard
- `install.sh` — inject `admiral_secret` via env var to the crew container instead of baking into `admission_policy.json`
- `academy/policies/default.json` (or equivalent policy template) — remove `admiral_secret` field from the seeded policy file; gateway reads it from env at startup
- `docs/configuration.md` — document new `HOST` default, `admiral_secret` env var, and the threat model for on-disk credential files
- `docs/auth.md` — document admiral secret delivery path change
