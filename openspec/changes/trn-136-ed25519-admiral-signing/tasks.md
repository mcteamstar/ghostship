## 1. Confirm cryptography availability in crew image

- [ ] 1.1 Inside the spec-ops crew container, verify `python3 -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey"` exits 0; if not, add `cryptography` to the spec-ops Containerfile and rebuild

## 2. transport/lifecycle.py — keypair generation

- [ ] 2.1 Replace `secrets.token_hex(32)` admiral secret generation with `Ed25519PrivateKey.generate()`; serialise the private seed as a 64-char hex string for storage in `DATA_DIR/secrets/<crew_id>.admiral_secret` (same path and format discipline as before)
- [ ] 2.2 Extract the 32-byte public key bytes and pass them (via stdin) to `inject_admiral_key.py` instead of the HMAC secret; remove the call to the old `inject_admiral_secret.py` script

## 3. transport/container_scripts/inject_admiral_key.py

- [ ] 3.1 Create `inject_admiral_key.py` (replacing `inject_admiral_secret.py`): reads raw public key bytes from stdin, writes them to `.admiral_public_key` (mode 0600) with fsync; same argv pattern as the old script (`<dest_path>`)
- [ ] 3.2 Update `lifecycle.py` to reference `inject_admiral_key.py`; remove or deprecate `inject_admiral_secret.py`

## 4. transport/captain.py — Ed25519 signing

- [ ] 4.1 Replace `hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()` with `Ed25519PrivateKey` loaded from the hex seed, `.sign(payload)`, and base64url-encoded result in `X-Admiral-Sig`
- [ ] 4.2 Update `_read_crew_secret` / secret loading to handle the new hex-encoded private seed format (should be transparent if format discipline is maintained)

## 5. crews/_base/admission/verify-admiral-sig — Ed25519 verification

- [ ] 5.1 Update `verify-admiral-sig` to read `.admiral_public_key` instead of `.admiral_secret`; update fallback path accordingly
- [ ] 5.2 Replace HMAC verification with Ed25519: load 32-byte public key, base64url-decode the `X-Admiral-Sig` header, call `public_key.verify(sig, payload)`; catch `InvalidSignature` → exit 1; handle missing key file → exit 2 (same retry/fallback logic as before)
- [ ] 5.3 Update `SECRET_PATH` constants to reference `.admiral_public_key`

## 6. Tests

- [ ] 6.1 Update unit tests for `_format_captain_mail` / admiral signing in `test_captain.py` to use Ed25519 keypair fixtures instead of HMAC secrets
- [ ] 6.2 Add unit tests for the new `inject_admiral_key.py` script covering: (a) public key written correctly, (b) mode 0600, (c) fsync called
- [ ] 6.3 Add unit tests for `verify-admiral-sig` covering: (a) valid Ed25519 sig → exit 0, (b) invalid sig → exit 1, (c) missing public key → exit 2
- [ ] 6.4 Run full unit test suite and confirm all tests pass

## 7. Documentation and validation

- [ ] 7.1 Update `docs/auth.md` threat model section: describe Ed25519 keypair model, what it protects (private key never in container → forgery impossible), and residual risks (public key substitution, replay attacks)
- [ ] 7.2 Run `openspec validate trn-136-ed25519-admiral-signing` and confirm no errors
