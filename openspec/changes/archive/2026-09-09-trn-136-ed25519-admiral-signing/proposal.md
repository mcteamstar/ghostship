## Why

The admiral signing mechanism uses HMAC with a shared secret: the transport holds the secret and injects a copy into the crew container. A compromised agent running as `kirocrew` can read and overwrite `.admiral_secret`, enabling it to forge Admiral mail that the crew accepts as legitimate. Asymmetric signing removes this attack — the crew container holds only the public key, which is useless for forgery.

## What Changes

- **Key generation**: at crew launch, generate an Ed25519 keypair instead of a random HMAC secret, *before* the crew container is created. Store the private key in `DATA_DIR/secrets/<crew_id>.admiral_secret` (same path, different content). Never inject the private key into the container.
- **Public key delivery**: deliver the Ed25519 public key to the container as a **Podman secret** (`podman secret create` + a `secrets` entry on `container_create`), mounted read-only at `.admiral_public_key` (root-owned, mode 0444) — not via container-exec/stdin injection. A read-only bind mount cannot be overwritten by the `kirocrew` process regardless of file permissions, and `CAP_SYS_ADMIN` (needed to remount it read-write) is already dropped from crew containers (TRN-93). This closes the public-key-substitution attack: a compromised agent can no longer forge Admiral mail by swapping in its own keypair.
- **Signing**: `captain.py` signs Admiral mail with Ed25519 (via `cryptography`) instead of HMAC. The `X-Admiral-Sig` header carries the base64url-encoded detached signature.
- **Verification**: `verify-admiral-sig` verifies against `.admiral_public_key` using Ed25519 instead of HMAC against `.admiral_secret`. `cryptography` is pinned into the `base-admission` image (confirmed absent from the current crew image — see Design).
- **`inject_admiral_secret.py`**: removed, not renamed. Public key delivery no longer goes through a container-exec script at all — Podman handles the mount.
- **`docs/auth.md`**: update the threat model section to describe the keypair model and the Podman-secret delivery mechanism that makes the public key immutable from inside the container.

No breaking changes to the `X-Admiral-Sig` header name or the `verify-admiral-sig` exit code contract (0 = valid, 1 = mismatch, 2 = key not found).

## Capabilities

### New Capabilities
_(none)_

### Modified Capabilities
- `crew-auth`: Admiral mail signing changes from HMAC shared secret to Ed25519 asymmetric keypair; crew containers hold only the public key, delivered as a read-only Podman secret so it cannot be overwritten from inside the container; the private key never leaves the transport.
- `secret-delivery-hardening`: the admiral public key is carved out of the stdin-injection pattern entirely and delivered as a Podman secret instead; other secrets (the private key's host-side persistence, `policy_signing_key`) keep the existing stdin-delivery pattern unchanged.
- `crew-lifecycle`: the Admiral keypair is established at `container_create` rather than as a setup step, so admiral-secret injection drops out of the ordered setup steps and the "secret present before the post-restart gateway" guarantee is replaced by "public key present from container start". The `os.fsync` durability requirement now applies to the host-side private seed, not to an in-container file.

## Impact

- `transport/podman.py` — new `secret_create`/`secret_remove` methods; `container_create` gains a `secrets` param (Podman secret mounted at `.admiral_public_key`, uid/gid 0, mode 0444).
- `transport/server.py` — crew launch reordered: generate the Ed25519 keypair and create the Podman secret *before* `container_create` (the secret must exist to be attached at creation time); on crew teardown/nuke, remove the Podman secret (`admiral-pubkey-<crew_id>`) alongside existing volume/network cleanup.
- `transport/lifecycle.py` — `_finish_crew_setup` no longer injects the public key (it's already mounted at container start); persists the private key as before.
- `transport/captain.py` — `_format_captain_mail` signs with Ed25519 private key; `_read_crew_secret` reads the private key.
- `transport/registry.py` — secret path and file format unchanged (still `<crew_id>.admiral_secret`); content changes from hex string to hex-encoded Ed25519 seed.
- `crews/_base/admission/Containerfile` — pin `cryptography` (confirmed not currently installed in any crew image layer).
- `crews/_base/admission/verify-admiral-sig` — verify with Ed25519 public key from `.admiral_public_key` instead of HMAC from `.admiral_secret`.
- `transport/container_scripts/inject_admiral_secret.py` — deleted; no replacement needed.
- `transport/constants.py` — new `ADMIRAL_PUBKEY_PATH`, the single named home for the mount point (deliberately outside the home and workspace volumes).
- `docs/auth.md` — threat model updated, including the corrected upgrade guidance (nuke + relaunch required; restart does not migrate a crew) and the mount path.
- `docs/security.md`, `docs/architecture.md` — the stdin-delivery description and the `inject_admiral_secret.py` reference are removed, since that script no longer exists.
- `tests/unit/` — update signing/verification tests; add coverage for `secret_create`/`secret_remove`.
