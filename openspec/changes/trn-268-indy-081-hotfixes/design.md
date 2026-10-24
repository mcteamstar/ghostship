# Design: indy-0.8.1 hotfixes (second round)

## Context

See proposal.md — Why. Three independent fixes:

1. `VERSION` is `0.8.0`; both `.claude-plugin/plugin.json` manifests are `0.8.0`. The `v0.8.1` CHANGELOG section, README, and RELEASING docs were already updated by `release-081-hotfixes` and TRN-266, but no release commit was made. The `release-gate` CI workflow rejects a PR into `main` when plugin manifest versions drift from `VERSION`.

2. `crews/spec-ops/Containerfile` clones `.agents` from `AGENTS_REF="main"` (floating HEAD). Current tip SHA of `mcteamstar/.agents` is `639a9bd0db07adb41b419a3ff1e9cd0ddd8b0374`.

3. `ghostship status` and `bin/install.sh` obtain the CA cert path from `podman volume inspect` (via `_portal_data_mountpoint`). On macOS that mountpoint is inside the Podman VM — e.g. `/var/home/user/…` — not the host filesystem. The operator cannot run `security add-trusted-cert` or drag-and-drop the file without first extracting it.

## Goals / Non-Goals

**Goals:** release-version consistency, reproducible crew image builds, actionable CA cert path on macOS.

**Non-Goals:** Changing how the certificate is provisioned; changing the Caddy TLS mode; building tooling to auto-trust the certificate; any structural change to `ghostship status` output on Linux.

## Decisions

### 1. VERSION bump via a single release commit
Update `VERSION`, both `.claude-plugin/plugin.json` files, and commit with message `release: v0.8.1`. Do not git-tag at this stage — the tag is applied to `main` after the PR merges, per RELEASING.md.

*Alternative:* bump in tasks.md as three separate checklist items. Rejected — they all belong in one commit to keep the release state atomic.

### 2. AGENTS_REF pinned to current tip SHA
Set `ARG AGENTS_REF="639a9bd0db07adb41b419a3ff1e9cd0ddd8b0374"` in `crews/spec-ops/Containerfile`. Update the adjacent comment to say the SHA must be bumped deliberately for each `.agents` update, and that a new SHA triggers a cache-less rebuild (the `LABEL org.ghostship.agents_ref=$AGENTS_REF` already causes `install.sh` to detect the change via `_baked_agents_ref`).

*Alternative:* pin to a git tag. `mcteamstar/.agents` currently has no published tags. Rejected until tags are established.

### 3. macOS CA cert extraction hint
On macOS (`sys.platform == "darwin"` in `ghostship`; `uname -s` == `Darwin` in `install.sh`), after printing the VM CA cert path, print:

```
  CA cert (VM path — to extract to host, run):
    podman machine ssh <machine> cat <vm-cert-path> > ~/ghost-academy-root.crt
  Then trust it: sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ~/ghost-academy-root.crt
```

`<machine>` is resolved from `GA_MACHINE_NAME` (default `ghost-academy`) in the CLI; from `${_MACHINE}` (already computed) in `install.sh`. `<vm-cert-path>` is the same value from `_portal_data_mountpoint` / `_CADDY_ROOT_CERT_PATH`.

The hint is only printed when `mountpoint is not None` (CLI) / `_CADDY_ROOT_CERT_PATH` does not contain "not yet created" (install.sh). On Linux the block is unchanged.

*Alternative:* use `podman machine ssh` to run a `podman volume inspect` and compute the host-side forwarded path. Rejected — there is no stable host-side path for the VM volume; the operator copy is simpler and idempotent.

## Risks / Trade-offs

- [The `security add-trusted-cert` command requires `sudo`] → Printed as a `sudo` command with clear label. Operator decides when to run it; install never runs it automatically.
- [AGENTS_REF SHA is frozen at planning time] → The SHA `639a9bd0db07adb41b419a3ff1e9cd0ddd8b0374` is the current `main` HEAD of `mcteamstar/.agents`. Ghost must confirm the SHA is still current at implementation time by running `git ls-remote https://github.com/mcteamstar/.agents.git HEAD` and using the live value if it has moved.
- [VERSION bump before merge could conflict with concurrent changes] → `VERSION`, plugin manifests, and `CHANGELOG` are touched by very few changes; the risk is low. If it occurs, resolve by keeping the higher version number.

## Migration Plan

No operator migration needed:
- VERSION change is transparent to running crews.
- AGENTS_REF change takes effect on the next `ghostship upgrade` (image rebuild).
- macOS hint is output-only; no config change required.

## Open Questions

None. All decisions are resolved.
