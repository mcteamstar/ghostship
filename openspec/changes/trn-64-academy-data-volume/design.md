## Context

See proposal.md — Why for the motivation.

The transport container currently receives `academy/` and `crews/` via six bind-mount entries in the generated `compose.yml`:

```yaml
- ${GHOSTSHIP_DIR}/academy/agents:/agents:ro
- ${GHOSTSHIP_DIR}/academy/skills:/skills:ro
- ${GHOSTSHIP_DIR}/academy/steering:/steering:ro
- ${GHOSTSHIP_DIR}/academy/policies:/policies:ro
- ${GHOSTSHIP_DIR}/academy/orders:/orders:ro
- ${GHOSTSHIP_DIR}/crews:/crews:ro
```

`GHOSTSHIP_DIR` is the absolute path of the repo checkout at install time. The `compose.yml` is written to `DATA_DIR` (a Podman-managed or user-configured path independent of the repo), but the six academy/crews entries point back into the repo. The compose file is otherwise fully self-contained — it is the mechanism used by `start.sh` and `uninstall.sh` — so the repo reference is the only remaining runtime dependency on the checkout.

`DATA_DIR` already has a read/write mount into the container at `/data`. The transport container's writable state (registry, auth file, crew workspaces) all live there. Adding the academy/crews snapshots to `DATA_DIR` requires no new volume.

## Goals / Non-Goals

**Goals:**
- Remove all runtime dependencies on the repo checkout path from the generated `compose.yml`
- Keep the transport container's internal mount points (`/agents`, `/skills`, etc.) identical so no transport code changes are needed
- Make reinstall (`./install.sh`) the explicit, documented update path for academy/crews content

**Non-Goals:**
- Live-reload of academy/crews content without reinstall — a deliberate non-goal; the copy-on-install model is the fix
- Modifying `uninstall.sh` or `start.sh` beyond what's needed (compose file path is already `DATA_DIR/compose.yml`)
- Moving the data volume itself or changing its mount point

## Decisions

### D1: Copy into DATA_DIR rather than a named Podman volume

**Decision:** Copy `academy/` and `crews/` into `${DATA_DIR}/academy/` and `${DATA_DIR}/crews/` using `cp -r` (or `rsync --delete` to handle deletions on reinstall). Mount from there in `compose.yml`.

**Alternatives considered:**
- *Named Podman volume*: Would need a new `podman volume create` call, a populate step, and a corresponding volume declaration in `compose.yml`. More moving parts; `DATA_DIR` is already bind-mounted and immediately accessible on the host without extra Podman commands.
- *Bake academy/crews into the transport image*: Would mean rebuilding the transport image on every skill or agent change, which is much heavier than a copy step. Rejected.

**Rationale:** `DATA_DIR` is the established place for install-time-generated, machine-local content. The directory is already present before the compose generation step. Adding two subdirectories there is zero-overhead and keeps the approach consistent with how `ga-kiro-auth` and `compose.yml` itself are managed.

### D2: rsync --delete for the copy step

**Decision:** Use `rsync -a --delete` rather than `rm -rf && cp -r` to keep the copy atomic in the failure case and to correctly remove files deleted from the repo between installs.

**Alternatives considered:**
- `cp -r` alone: Does not remove stale files when a skill or agent is deleted from the repo between reinstalls — stale files would persist in the data volume.
- `rm -rf ${DATA_DIR}/academy && cp -r`: Works but briefly leaves the directory absent, which could cause issues if a running transport is somehow reading the directory mid-install (unlikely given the compose restart that follows, but unnecessarily risky).

**Rationale:** `rsync -a --delete` is idempotent, handles deletes, and is available on all supported platforms. Fall back to `rm -rf && cp -r` if rsync is absent (it is not a listed prerequisite).

### D3: Compose entries use DATA_DIR-relative absolute paths

**Decision:** The generated `compose.yml` uses the resolved absolute path of `${DATA_DIR}/academy/agents` etc., not a relative path or a Compose `volumes:` top-level declaration.

**Rationale:** This is consistent with the existing compose generation approach — `DATA_DIR` and `PODMAN_SOCK` are already baked as absolute paths at generation time. No new Compose syntax is introduced.

## Risks / Trade-offs

- [Risk] `rsync` not installed → install fails at copy step.  
  Mitigation: detect `rsync` availability; fall back to `rm -rf && cp -r` with a log message. Both approaches are correct; rsync is preferred but not required.

- [Risk] Users editing `academy/` files expect live reload.  
  Mitigation: documentation clearly states reinstall is required. This is a deliberate trade-off for robustness — a live bind-mount silently breaks when the repo moves; a copy never does.

- [Risk] `DATA_DIR/academy` and `DATA_DIR/crews` grow stale after a major repo restructure.  
  Mitigation: reinstall always overwrites (via `--delete`). The stale state is only reachable if a user starts the transport without reinstalling, which the docs will call out.

## Migration Plan

1. Run `./install.sh` — the copy step runs, `compose.yml` is regenerated with the new mount paths, and the transport container is restarted. No manual migration required.
2. The old bind-mount entries (repo-path-based) disappear from `compose.yml` after regeneration. No rollback step — the previous `compose.yml` can be restored by reverting `install.sh` and re-running.

## Open Questions

None — the approach is fully determined by the existing `DATA_DIR` structure and `compose.yml` generation pattern.
