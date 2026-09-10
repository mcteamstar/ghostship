> **Reopened 2026-09-09** after a post-implementation review of the first pass
> (branch `b136/trn-136-ed25519-admiral-signing`). Two blocking defects were
> found: the secret mount target broke crew launch, and `verify-admiral-sig`
> corrupted roughly 1 in 21 public keys. Tasks whose stated outcome is now wrong
> or was never actually verified are unticked below; see design.md for the two
> new decisions.

## 1. Pin cryptography into the crew image

- [x] 1.1 Add `cryptography` (pinned version) to `crews/_base/admission/Containerfile`; rebuild and verify `python3 -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey"` exits 0 inside a spec-ops container. **Record the command and its output in the PR** — this was previously ticked without evidence and the shipped image did not carry the package

## 2. transport/podman.py — Podman secret support

- [x] 2.1 Add `secret_create(name: str, data: bytes) -> None` (`POST /libpod/secrets/create`) and `secret_remove(name: str) -> None` (`DELETE /libpod/secrets/{name}`) to `PodmanClient`
- [x] 2.2 Add a `secrets` parameter to `container_create` — one entry: source = secret name, target = `ADMIRAL_PUBKEY_PATH` (`/run/secrets/.admiral_public_key`, **outside** any volume mount point), uid = 0, gid = 0, mode = 0o444. The original `{KIRO_CREW_DIR}/.admiral_public_key` target is what broke launch (see design.md, "the secret target must live outside the home volume"). Only the directory changes; the filename stays `.admiral_public_key` so the dozen bare-filename references in specs, docs and tests stay correct

## 3. transport/server.py + transport/lifecycle.py — keypair generation before container_create

- [x] 3.1 In the crew launch flow in `server.py`, before the call to `podman.container_create`: generate an Ed25519 keypair (`Ed25519PrivateKey.generate()`); persist the hex-encoded private seed via `_write_crew_secret(crew_id, ...)`; call `podman.secret_create(f"admiral-pubkey-{crew_id}", public_key_bytes)`
- [x] 3.2 Pass the secret name/target into `container_create`'s new `secrets` param
- [x] 3.3 Remove the old post-start `inject_admiral_secret.py` exec call and the `admiral_secret = secrets.token_hex(32)` generation from `_finish_crew_setup` in `lifecycle.py`
- [x] 3.4 Delete `transport/container_scripts/inject_admiral_secret.py` — no replacement needed, Podman handles delivery
- [x] 3.5 Update `_cleanup_crew` and the nuke path to call `podman.secret_remove(f"admiral-pubkey-{crew_id}")` alongside existing volume/network cleanup
- [x] 3.6 Define `ADMIRAL_PUBKEY_PATH = "/run/secrets/.admiral_public_key"` as a module-level constant next to `KIRO_CREW_DIR` and use it in `server.py` instead of an inline f-string, so the transport and the verifier have one named path to keep in step
- [x] 3.7 Drop the `admiral_secret: str = ""` default on `_finish_crew_setup` and make it a required keyword argument — the default would silently record `_secret_identifier("")` in `crews.json` if a future caller omitted it

## 4. transport/captain.py — Ed25519 signing

- [x] 4.1 Replace `hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()` with `Ed25519PrivateKey` loaded from the hex seed, `.sign(payload)`, and base64url-encoded result in `X-Admiral-Sig`
- [x] 4.2 Update `_read_crew_secret` / secret loading to handle the new hex-encoded private seed format (should be transparent if format discipline is maintained)

## 5. crews/_base/admission/verify-admiral-sig — Ed25519 verification

- [x] 5.1 Point `PUBKEY_PATH` at `/run/secrets/.admiral_public_key` and **delete** `PUBKEY_PATH_FALLBACK` — nothing mounts anything at `/home/kirocrew/workplace/.admiral_public_key`, so the fallback branch is unreachable. Add a comment naming `ADMIRAL_PUBKEY_PATH` in the transport as the value this must match
- [x] 5.2 Replace HMAC verification with Ed25519: load 32-byte public key, base64url-decode the `X-Admiral-Sig` header, call `public_key.verify(sig, payload)`; catch `InvalidSignature` → exit 1; handle missing key file → exit 2 (same retry/fallback logic as before)
- [x] 5.3 Update the path constants and the retry loop to match 5.1 (single path, no fallback iteration)
- [x] 5.4 **Remove the `.strip()` from `pubkey_bytes = f.read().strip()`** — it silently truncates any raw Ed25519 public key that begins or ends with an ASCII whitespace byte (measured: 4.75% of generated keys), which makes `from_public_bytes` raise `ValueError` and the crew exit 2 for its whole life. Replace it with an explicit `len(pubkey_bytes) != 32 → exit 2` guard

## 6. Tests

- [x] 6.1 Update unit tests for `_format_captain_mail` / admiral signing in `test_captain.py` to use Ed25519 keypair fixtures instead of HMAC secrets
- [x] 6.2 Add unit tests for `PodmanClient.secret_create` / `secret_remove` and for the new `secrets` param on `container_create`
- [x] 6.3 Add unit tests for `verify-admiral-sig` covering: (a) valid Ed25519 sig → exit 0, (b) invalid sig → exit 1, (c) missing public key → exit 2
- [x] 6.4 **Prove the mount works against a real crew, through the transport only.** Launch a crew via the `ghostship` MCP tools, confirm it reaches `running` (the previous target made the entrypoint die on `config.json` with `Permission denied`, so the gateway never bound), then send a standing order via `captain` and confirm the crew accepts it as genuine Admiral mail. Do not `podman exec` into the crew to check the file; if that feels necessary, the transport is missing a capability. Paste the crew id and the observed result in the PR
- [x] 6.5 Run the full unit test suite. Confirm the failure set matches `release/0.3.2` exactly (2 failures, 11 errors, all in `test_recovery` and `test_dashboard_session`, all pre-existing and environmental) and that no new failure appears
- [x] 6.6 Add a **deterministic** regression test for 5.4: write a public key crafted so its first byte and (in a second case) its last byte are ASCII whitespace (`0x20`, `0x0a`), and assert `verify-admiral-sig` still exits 0 for a valid signature. The existing tests generate random keypairs, so they only catch this a few percent of the time and a single green run means nothing
- [x] 6.7 Update the path literals the verifier tests patch (`test_admiral_sig.py`) and the expected target in `test_podman.py` to match the new `ADMIRAL_PUBKEY_PATH`, and drop the fallback-path substitution now that 5.1 removes it

## 7. Documentation and validation

- [x] 7.1 Update `docs/auth.md`: the Ed25519 keypair model, the Podman-secret delivery mechanism that makes the public key immutable from inside the container (read-only mount + dropped `CAP_SYS_ADMIN`), the residual replay-attack risk, and the corrected mount path (it currently documents `/home/kirocrew/.kiro/crew/.admiral_public_key` in roughly six places)
- [x] 7.2 Add an explicit operator-facing upgrade note (docs/auth.md and/or release notes): existing crews must be nuked and relaunched to adopt Ed25519 signing — a transport restart or crew restart does not migrate them
- [x] 7.3 Sync `openspec/specs/crew-lifecycle/spec.md` — line 175 still requires `.admiral_secret` be written to `/home/kirocrew/.kiro/crew/` before the post-restart gateway, which this change makes false. The first pass synced `crew-auth` and `secret-delivery-hardening` but missed this one
- [x] 7.4 Update `docs/security.md` — the "Admiral secret delivery via stdin" section still describes the old mechanism and names `inject_admiral_secret.py`, a file this change deletes
- [x] 7.5 Update `docs/architecture.md` — lines 88, 440 and 476 still describe the HMAC-over-stdin model and `~/.kiro/crew/.admiral_secret` (mode 0600)
- [x] 7.6 Reconsider the `cryptography==43.0.1` pin in `transport/requirements.txt`. The transport already resolves 50.0.1 transitively via `PyJWT[crypto]` (`cryptography>=3.4.0`), so this pin is an ~18-month downgrade of a security-critical library inside a security change. Either drop it and rely on the transitive resolution, or pin forward to the version the image already carries and match the crew image to it. Note design.md's claim that it is "already in `requirements.txt` via `pyjwt[crypto]`" is not literally true — it is transitive, not declared
- [x] 7.7 Run `openspec validate trn-136-ed25519-admiral-signing` and confirm no errors
