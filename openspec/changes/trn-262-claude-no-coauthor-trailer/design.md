# Design

## Context

See proposal.md for why.

- The spec-ops Containerfile copies `crews/spec-ops/toolchains/` to `/tmp/toolchains/` and runs `<name>.sh` as root for each name in `AGENT_TOOLCHAINS`, then deletes `/tmp/toolchains`. `claude.sh` installs the pinned `claude-agent-acp@0.79.0` and `claude-code@2.1.293` and nothing else.
- The crew's home volume is mounted at `/home/kirocrew` (`transport/podman.py`). Podman copies image content into a named volume only on its first mount, and claude OAuth injection rewrites `~/.claude/` at launch.
- KiroCrew writes `<work_dir>/.claude/settings.local.json` (`permissions.defaultMode: "bypassPermissions"`) per session.
- Claude Code (per https://code.claude.com/docs/en/settings-reference and /managed-settings):
  - `attribution.commit` / `attribution.pr` set to `""` hide the commit trailer and the PR text respectively. `includeCoAuthoredBy` is deprecated since v2.0.62 and is ignored once `attribution` is set.
  - On Linux, managed settings are read from `/etc/claude-code/managed-settings.json`. They outrank CLI, local, project and user settings, and a commit-trailer opt-out is honoured from any tier.
  - The Agent SDK loads managed settings regardless of `settingSources`.

## Goals / Non-Goals

**Goals:**
- One build-time file that turns attribution off for every claude crew, with no transport or KiroCrew change.

**Non-Goals:**
- Making attribution configurable from `ghostship.yaml`. The image is built without the operator's runtime config. Off is the only behaviour shipped.
- Stripping trailers from commits already made.

## Decisions

### 1. Managed settings, not `~/.claude/settings.json`
Write `/etc/claude-code/managed-settings.json`. A file under `~/.claude/` sits on the home volume, so a crew with an existing volume would never see it, and OAuth injection could replace it. A transport-side write at launch would work, but it adds launch-time code for what is a static property of the image. The managed tier also outranks the `settings.local.json` that KiroCrew writes.

*Alternative considered:* `--settings` / environment variable through `claude-agent-acp`. Rejected because it needs adapter or KiroCrew changes and is lower precedence than managed.

### 2. The settings live in a checked-in JSON file
Add `crews/spec-ops/toolchains/claude-managed-settings.json` containing exactly:

```json
{ "attribution": { "commit": "", "pr": "" } }
```

`claude.sh` installs it with `install -D -m 0644 /tmp/toolchains/claude-managed-settings.json /etc/claude-code/managed-settings.json`. A separate file can be validated by a unit test without building an image, and the toolchain loop never treats it as a toolchain because it only runs `<name>.sh`.

Use the `{commit, pr}` object rather than `"attribution": false`. Both work on the pinned 2.1.293, but `false` needs ≥ 2.1.281, while empty strings work on every version since `attribution` was introduced. That keeps a future downgrade of the pin safe. Don't set `includeCoAuthoredBy`: it is deprecated and ignored once `attribution` is present.

### 3. Verification goes over the transport
After `ghostship upgrade`, the live check launches a claude crew and dispatches an agent to make a commit, then evacs and inspects it. Per the transport-only rule, no `podman exec` against the crew.

## Risks / Trade-offs

- [`claude-agent-acp` might bypass managed settings] → The SDK docs say managed policy always loads. The live check in task 3.2 confirms it against the pinned adapter.
- [Model still writes a trailer by habit, ignoring the setting] → The setting removes Claude Code's instruction to add one. If a trailer still appears in the live check, add a steering line as a follow-up rather than widening this change.
- [Managed settings is an "enterprise" tier that future keys could lock down] → The file holds one key. Anything else added later goes through review.

## Migration Plan

`ghostship upgrade` rebuilds the image (the toolchain layer changes, so it isn't cached). Relaunch claude crews to pick it up, since existing containers keep their image. Rollback is reverting the commit and upgrading again.
