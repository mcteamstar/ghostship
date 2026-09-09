## 1. Pin cryptography into the crew image

- [ ] 1.1 Add `cryptography` (pinned version) to `crews/_base/admission/Containerfile`; rebuild and verify `python3 -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey"` exits 0 inside a spec-ops container

## 2. transport/podman.py — Podman secret support

- [ ] 2.1 Add `secret_create(name: str, data: bytes) -> None` (`POST /libpod/secrets/create`) and `secret_remove(name: str) -> None` (`DELETE /libpod/secrets/{name}`) to `PodmanClient`
- [ ] 2.2 Add a `secrets` parameter to `container_create` — one entry: source = secret name, target = `{KIRO_CREW_DIR}/.admiral_public_key`, uid = 0, gid = 0, mode = 0o444

## 3. transport/server.py + transport/lifecycle.py — keypair generation before container_create

- [ ] 3.1 In the crew launch flow in `server.py`, before the call to `podman.container_create`: generate an Ed25519 keypair (`Ed25519PrivateKey.generate()`); persist the hex-encoded private seed via `_write_crew_secret(crew_id, ...)`; call `podman.secret_create(f"admiral-pubkey-{crew_id}", public_key_bytes)`
- [ ] 3.2 Pass the secret name/target into `container_create`'s new `secrets` param
- [ ] 3.3 Remove the old post-start `inject_admiral_secret.py` exec call and the `admiral_secret = secrets.token_hex(32)` generation from `_finish_crew_setup` in `lifecycle.py`
- [ ] 3.4 Delete `transport/container_scripts/inject_admiral_secret.py` — no replacement needed, Podman handles delivery
- [ ] 3.5 Update `_cleanup_crew` and the nuke path to call `podman.secret_remove(f"admiral-pubkey-{crew_id}")` alongside existing volume/network cleanup

## 4. transport/captain.py — Ed25519 signing

- [ ] 4.1 Replace `hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()` with `Ed25519PrivateKey` loaded from the hex seed, `.sign(payload)`, and base64url-encoded result in `X-Admiral-Sig`
- [ ] 4.2 Update `_read_crew_secret` / secret loading to handle the new hex-encoded private seed format (should be transparent if format discipline is maintained)

## 5. crews/_base/admission/verify-admiral-sig — Ed25519 verification

- [ ] 5.1 Update `verify-admiral-sig` to read `.admiral_public_key` instead of `.admiral_secret`; update fallback path accordingly
- [ ] 5.2 Replace HMAC verification with Ed25519: load 32-byte public key, base64url-decode the `X-Admiral-Sig` header, call `public_key.verify(sig, payload)`; catch `InvalidSignature` → exit 1; handle missing key file → exit 2 (same retry/fallback logic as before)
- [ ] 5.3 Update `SECRET_PATH` constants to reference `.admiral_public_key`

## 6. Tests

- [ ] 6.1 Update unit tests for `_format_captain_mail` / admiral signing in `test_captain.py` to use Ed25519 keypair fixtures instead of HMAC secrets
- [ ] 6.2 Add unit tests for `PodmanClient.secret_create` / `secret_remove` and for the new `secrets` param on `container_create`
- [ ] 6.3 Add unit tests for `verify-admiral-sig` covering: (a) valid Ed25519 sig → exit 0, (b) invalid sig → exit 1, (c) missing public key → exit 2
- [ ] 6.4 Verify (manually or via an integration check) that the Podman secret mounts correctly at `.kiro/crew/.admiral_public_key` on the home volume — confirm the parent directory resolves at `container_create` time
- [ ] 6.5 Run full unit test suite and confirm all tests pass

## 7. Documentation and validation

- [ ] 7.1 Update `docs/auth.md` threat model section: describe the Ed25519 keypair model, the Podman-secret delivery mechanism that makes `.admiral_public_key` immutable from inside the container (read-only mount + dropped `CAP_SYS_ADMIN`), and the residual replay-attack risk
- [ ] 7.2 Add an explicit operator-facing upgrade note (docs/auth.md and/or release notes): existing crews must be nuked and relaunched to adopt Ed25519 signing — a transport restart or crew restart does not migrate them
- [ ] 7.3 Run `openspec validate trn-136-ed25519-admiral-signing` and confirm no errors
