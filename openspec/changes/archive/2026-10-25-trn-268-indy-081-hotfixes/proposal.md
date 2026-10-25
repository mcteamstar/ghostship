# Proposal: indy-0.8.1 hotfixes (second round)

## Why

Live-crew testing of the 0.8.1 release (which landed the TRN-262/263/264/265 feature work and the first hotfix batch `release-081-hotfixes`) uncovered a second set of small defects. None needs its own change, but together they would prevent a clean `v0.8.1` release tag:

- `VERSION` still reads `0.8.0` even though the CHANGELOG, RELEASING.md, and both Claude-plugin manifests were already written for `v0.8.1`. The mismatch trips the `release-gate` CI check that rejects a PR into `main` when any manifest version drifts from `VERSION`.
- The Containerfile for `spec-ops` clones `.agents` from `AGENTS_REF=main`, meaning a HEAD-of-main drift between image builds changes crew behaviour unpredictably and without a code review. The first hotfix batch noted this as a deliberate deferral pending a decision; the decision is to pin to the current tip SHA now.
- On macOS the CA certificate path that `ghostship status` and `install.sh` print is inside the Podman VM (`/var/home/user/…`), not the host filesystem. Operators cannot act on it without a `podman machine ssh` or `podman cp` command. The `transport/tls` spec requires the path to be surfaced; it does not require it to be host-usable — but given that every macOS user hits this, printing the host-usable extraction command alongside the VM path is the minimal practical fix.
- The stray `ghostship auth` call during a non-interactive install: when `_INTERACTIVE_MODE` is false, the install skips the auth block entirely, so this is not a live bug. Investigation confirmed the call is correctly gated. No code change needed; close out the deferred item.
- `token_signing.key` sandbox failure and zombie Raven cycles: investigation shows these were one-time incidents caused by a specific kiro-cli 2.27+ sandbox-bypass config that `_patch_crew_config` already injects. The autonomous-orchestration spec and code are correct; no further change is needed.

Where each remaining fix comes from:

| Fix | Introduced or exposed by |
|---|---|
| VERSION not bumped to 0.8.1 | release-081-hotfixes and TRN-266 (default-model) both landed content for v0.8.1 but no release commit was made |
| AGENTS_REF floating on `main` | TRN-264 baked `.agents` into the image; the SHA was left floating pending a decision |
| macOS CA path not host-usable | First hotfix batch fixed the volume lookup but explicitly deferred the VM-path usability gap |

## What Changes

- `VERSION` → `0.8.1`; both `.claude-plugin/plugin.json` manifests → `"version": "0.8.1"`. One release commit satisfies the `release-gate` check.
- `crews/spec-ops/Containerfile`: `AGENTS_REF` default value changed from `"main"` to the current tip SHA of `mcteamstar/.agents`. The comment updated to say the SHA must be bumped manually for each `.agents` update.
- `ghostship status` and `bin/install.sh`: when running on macOS (detected as `sys.platform == "darwin"` in the CLI, or `uname` in the shell script) and `GA_PORTAL_TLS_MODE=internal`, print a `podman machine ssh` extraction hint alongside the VM CA cert path so operators can copy it to the host trust store without looking up the syntax.
- **Out of scope (closed out):**
  - Stray `ghostship auth` call: the `_INTERACTIVE_MODE` guard is correct; no change needed.
  - `token_signing.key` sandbox failure: caused by the sandbox transition already addressed in `_patch_crew_config`; no change needed.
  - Zombie Raven cycles: `_steer_captain_checkin` 400-on-continue handling is correct; no change needed.
  - Changing the recovery logic for which HTTP statuses trigger cookie refresh — that is a separate spec question.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `transport/tls`: the "Internal CA root certificate path is surfaced" requirement SHALL additionally state that on macOS the output includes a `podman machine ssh` host-extraction command, so operators can copy the certificate to the host trust store without looking up the VM path syntax.

## Impact

- **`VERSION`**, **`.claude-plugin/plugin.json`** (×2): version string `0.8.0` → `0.8.1`.
- **`crews/spec-ops/Containerfile`**: `AGENTS_REF` default SHA pinned.
- **`ghostship`** (CLI): `cmd_status` macOS branch prints extraction hint.
- **`bin/install.sh`**: post-install CA path block adds macOS extraction hint.
- **`openspec/specs/transport/tls/spec.md`**: extend "Internal CA root certificate path is surfaced" with macOS host-extraction requirement.
- **Operators**: `ghostship upgrade`; no behaviour change on Linux.
