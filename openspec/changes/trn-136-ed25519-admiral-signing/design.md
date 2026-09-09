## Context

See proposal.md for motivation.

Current state:
- `lifecycle.py` generates `secrets.token_hex(32)` as `admiral_secret`
- `inject_admiral_secret.py` writes it to `.admiral_secret` (mode 0600) in the container
- `captain.py` signs with `hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()`; the `X-Admiral-Sig` header carries the hex HMAC
- `verify-admiral-sig` reads `.admiral_secret`, recomputes the HMAC, compares with `hmac.compare_digest`
- The private key is stored at `DATA_DIR/secrets/<crew_id>.admiral_secret` (written by `registry._write_crew_secret`)
- `cryptography` is resolved transitively in the transport image via `PyJWT[crypto]` (`cryptography>=3.4.0`), which currently yields 50.0.1. It is *not* declared in `requirements.txt` (corrected 2026-09-09; the original note here claimed it was, which led the first pass to add a pin that downgrades it)

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

Checked directly: `crews/_base/admission/Containerfile`, `crews/_base/graduation/Containerfile`, and `crews/spec-ops/Containerfile` install Node.js and the OpenSpec CLI but never `pip install` anything. The base image (`ghcr.io/kirodotdev/kirocrew:0.5.0`) is not guaranteed to carry `cryptography` — see the pinning decision below.

Crew containers are created with `cap_drop: ["CAP_NET_RAW", "CAP_SYS_ADMIN"]` and `no_new_privileges: true` (`transport/podman.py:206-209`, TRN-93). Podman secrets mount as read-only bind mounts; remounting one read-write requires `CAP_SYS_ADMIN`, which crew containers don't have.

`crew_id` is assigned before `container_create` is called (`transport/server.py:2389`), so a Podman secret can be created and attached to the container spec at creation time.

`_reconcile_registry` (`transport/lifecycle.py:1172`) only stops/starts the *existing* container on its existing rootfs — it never removes and recreates it. Neither a rebuilt crew image (a new `verify-admiral-sig` binary, baked in at build time via `COPY`) nor a newly-attached Podman secret reaches an already-created crew via restart; only container recreation (nuke + relaunch) picks up either.

## Goals / Non-Goals

**Goals:**
- Private key never enters the container, ever.
- The public key file is immutable from inside the container: a compromised agent process cannot overwrite `.admiral_public_key` to substitute a keypair it controls.
- `X-Admiral-Sig` header format changes minimally — same header name, value changes from hex HMAC to base64url-encoded Ed25519 signature.
- Exit code contract of `verify-admiral-sig` unchanged (0/1/2).
- Existing crews break on upgrade (intentional — the `.admiral_secret` file they hold is no longer valid; they need a full nuke + relaunch, not just a restart, to adopt the new image and the Podman-secret-mounted public key).

**Non-Goals:**
- Replay protection — out of scope for this change (acknowledged residual risk in TRN-136).
- Migrating existing running crews in-place — not possible via restart (see Decision below); operators must nuke and relaunch each crew after upgrading.

## Decisions

### Decision: Raw bytes for key storage and wire format

Store private key as raw 32-byte Ed25519 seed bytes (hex-encoded for the file, same as the current HMAC secret format). Store public key as raw 32-byte bytes (base64url-encoded for the wire `X-Admiral-Sig` value). This avoids PEM overhead and matches the simplicity of the current hex approach.

`DATA_DIR/secrets/<crew_id>.admiral_secret` changes from a 64-char hex HMAC secret to a 64-char hex representation of the 32-byte Ed25519 private seed. Same file, same path, same format discipline — just different cryptographic content. Reading code that does `hex.decode()` stays compatible.

### Decision: Signature encoding in X-Admiral-Sig

Current: `X-Admiral-Sig: <64-char hex HMAC>`
New: `X-Admiral-Sig: <88-char base64url Ed25519 signature>`

The header name is unchanged. The value format changes. Any tool that parses the header must update its parser — there are exactly two: `captain.py` (producer) and `verify-admiral-sig` (consumer). Both are in this change.

**Alternative considered**: keep hex encoding for the signature. Rejected — Ed25519 signatures are 64 bytes; hex would be 128 chars vs 88 chars base64url. Base64url is standard for this use case.

### Decision: Public key delivered via Podman secret, not container-exec injection

Instead of writing the public key into the container via `podman exec` + stdin (the pattern used for the HMAC secret and still used for `policy_signing_key`), create a Podman secret (`podman secret create admiral-pubkey-<crew_id>`, containing the raw 32-byte public key) and attach it to the container spec at `container_create` time: target `.admiral_public_key` inside `KIRO_CREW_DIR`, `uid: 0`, `gid: 0`, `mode: 0444`.

This makes the file genuinely immutable from inside the container, not just conventionally protected:
- It's a read-only bind mount — `kirocrew` cannot write to it no matter what the file's Unix permissions say, because the mount itself refuses writes.
- Undoing that would require remounting it read-write, which needs `CAP_SYS_ADMIN` — already dropped from crew containers (`no_new_privileges: true`, `cap_drop: [CAP_NET_RAW, CAP_SYS_ADMIN]`, TRN-93).

This directly closes the public-key-substitution risk that a stdin-injected, kirocrew-owned 0600 file could not close: a compromised agent running as the same user that owns the file can simply overwrite it, generate its own keypair, and self-sign forged Admiral mail that `verify-admiral-sig` would then report as valid.

Consequence: the keypair (or at least the public half) must exist and be registered as a Podman secret *before* `container_create` runs, so key generation moves from `_finish_crew_setup` (post-start) to the pre-create step in `server.py`'s launch flow. `inject_admiral_secret.py` / `inject_admiral_key.py` is deleted, not renamed — there's no longer a container-exec injection step for this secret.

Podman secrets are a global-namespace object (not scoped to a container), so the name must be unique per crew (`admiral-pubkey-<crew_id>`) and must be explicitly removed (`podman secret rm`) in `_cleanup_crew` and the nuke path, or they leak across crew lifecycles.

**Alternative considered**: write `.admiral_public_key` as a regular file owned by `root`, mode `0644`, via an exec run as a specific non-default user. Rejected — this relies on `kirocrew` never gaining privilege escalation, which happens to be true today but is a weaker, more implicit guarantee than a mount the kernel refuses to let `kirocrew` write to regardless of capabilities the container might gain in the future. It would also still need a new parameter on `container_exec_stdin` to run as a specific user, so it isn't materially simpler to implement.

### Decision: the secret target must live outside the home volume

*Added 2026-09-09 after the first implementation pass failed to launch.*

The target is `/run/secrets/admiral_public_key`, **not** `{KIRO_CREW_DIR}/.admiral_public_key`. Nesting the secret inside the home volume is what broke launch, and the mechanism is worth recording because it is not obvious.

The crew image does not ship `/home/kirocrew/.kiro` at all; the entrypoint creates that tree at runtime as `kirocrew` (uid 1000). When the secret target is `/home/kirocrew/.kiro/crew/.admiral_public_key`, Podman must materialise the parent directories itself in order to place the bind mount, and it creates them `root:root 0755`. The entrypoint then cannot write into its own config directory:

```
kirocrew-entrypoint: 138: cannot create /home/kirocrew/.kiro/crew/config.json: Permission denied
```

The container exits 2, the gateway never binds, and `launch()` fails with "Gateway not ready within 60s". Reproduced directly against `localhost/spec-ops:latest`: with the nested secret, `.kiro/crew` in the volume is `root:root` and holds only a zero-byte bind-mount stub; without it, the same directory is `1000:1000` and holds `config.json`.

The `uid`/`gid` fields on the secret do not help. They set ownership of the secret *file*, not of the directories Podman creates on the way to it; a run with `uid=1000,gid=1000` still produced a `root:root` parent and the same failure.

Mounting at `/run/secrets/` was verified against the same image: the entrypoint seeds `config.json` normally, the gateway starts, the key reads back as `-r--r--r-- root root` 32 bytes as uid 1000, and it survives the stop/start cycle `_finish_crew_setup` performs. The immutability argument is untouched, since it is still a read-only bind mount with `CAP_SYS_ADMIN` dropped.

Only the *directory* changes. The filename stays `.admiral_public_key`, giving `/run/secrets/.admiral_public_key`. A dotfile in a secrets directory is slightly unusual, but roughly a dozen references across the specs, `docs/auth.md` and the tests name the file without a path, and they all stay correct this way. In a security change, a smaller and more mechanical diff is worth more than the tidier name.

**Generalisation worth holding on to:** any mount placed inside `/home/kirocrew` or the workspace volume leaves its parent directories root-owned, which breaks anything that later writes there as `kirocrew`. Prefer a path outside the volumes for injected, immutable material.

### Decision: never trim raw key bytes

*Added 2026-09-09 after the first implementation pass.*

`verify-admiral-sig` read the key as `f.read().strip()`. The file holds a **raw 32-byte** Ed25519 public key, not text, so `.strip()` removes any leading or trailing byte that happens to be ASCII whitespace. Measured over 20,000 generated keys, 4.75% start or end with one of `0x09 0x0a 0x0b 0x0c 0x0d 0x20`, and each of those truncates to 31 bytes, raises `ValueError` from `from_public_bytes`, and exits 2 for the entire life of that crew.

Read raw key material with no normalisation, and assert the length explicitly (`len(pubkey_bytes) != 32 → exit 2`) rather than letting a malformed length surface as a generic decode error.

This also has a testing consequence recorded in tasks 6.6: because the existing tests generate random keypairs, they reproduce this only a few percent of the time. A single green suite run is not evidence. The regression test must craft a key with whitespace bytes at the boundaries.

### Decision: pin `cryptography` into `base-admission` now, not as a runtime check

Rather than have task 1.1 discover at implementation time that `cryptography` may be missing and improvise a fallback, pin `cryptography` into `crews/_base/admission/Containerfile` (every composition inherits from it) as part of this change, since it's confirmed absent from every layer of the current crew image build.

**Fallback** (only if pinning it there turns out to be impractical): vendor a minimal pure-Python Ed25519 verify implementation (~100 lines) into `verify-admiral-sig` instead of depending on the package.

### Decision: Upgrade path for existing crews

Neither the new `verify-admiral-sig` binary (baked into the image, updated only when the image is rebuilt and the container is recreated from it) nor the Podman-secret-mounted public key (attached only at `container_create`) reaches an existing crew container via restart. `_reconcile_registry` only stops/starts the same container on the same rootfs — it cannot deliver either change to a crew that isn't recreated.

This means: after this change ships, every crew created before the upgrade keeps running the old HMAC image and secret until it is explicitly nuked and relaunched. There is no gradual, restart-driven migration window like the original HMAC-rotation design assumed — nuke and relaunch is the only path, not a fallback for impatient operators. Document this plainly as a required operator action in the release notes and `docs/auth.md`, not left implicit.

## Risks / Trade-offs

**`cryptography` not available in crew container** → Mitigated by pinning it into `base-admission` up front (see Decision above) rather than discovering the gap during implementation.

**Podman secret mount target must exist before container start** → **Resolved 2026-09-09, and this risk is what sank the first pass.** Podman does create intermediate directories for a secret mount target, but it creates them `root:root`, which makes the crew's own config directory unwritable and kills the entrypoint. The answer is not to pre-seed `.kiro/crew/` but to move the target out of the volume entirely. See "Decision: the secret target must live outside the home volume". The original instruction to confirm this during implementation was correct and was ticked (task 6.4) without being carried out.

**Existing crews break on upgrade** → Documented above: this is not a short window, it's permanent until the operator nukes and relaunches. Acceptable for a security change, but must be called out explicitly rather than implied to resolve itself.

**`verify-admiral-sig` exit 1 (mismatch) not handled gracefully in orders** → Raven's current instructions treat exit 2 as transient (hold) but exit 1 as a hard rejection. After this change, a crew running the old HMAC verifier against a new Ed25519 signature will exit 1 and Raven will escalate. This is correct behaviour — it surfaces the upgrade mismatch clearly rather than silently retrying.

## Migration Plan

1. Deploy new transport and crew images (`install.sh` rebuilds `localhost/spec-ops:latest` etc. as usual — source hash / version changes).
2. New crew launches use the new flow automatically: keypair generated before `container_create`, public key attached as a Podman secret at creation.
3. Existing crews (containers created before the upgrade) are unaffected by the transport restart — they keep the old image and the old `.admiral_secret` HMAC file. `_reconcile_registry` does not and cannot migrate them; it only restarts the same container on the same rootfs.
4. Operator action required: nuke and relaunch every crew after upgrading to actually adopt Ed25519 signing fleet-wide.
5. No config changes needed.
