# Design: Volume-direct evac for stopped crews

See `proposal.md` for motivation and problem statement.

## Context

The transport manages crew containers via the Podman REST API (ghost-academy socket at
`/run/user/1000/ghost-academy/podman.sock`). Each crew has a workspace volume
`gs-vol-{crew_id}` backed by a plain directory on the host filesystem. The transport
container does not have the host's volume storage path bind-mounted, so direct path reads
are not viable. The volume export API (`GET /libpod/volumes/{name}/export`) streams the
entire volume as tar — functional but expensive for targeted reads.

The current evac path (`container_archive_get` / `container_exec`) requires the crew
container to be running and goes through a double start cycle + gateway wait on restart,
costing 2–3s minimum and failing entirely if the container won't start.

Empirical results from the academy VM (`academy.penguin-piano.ts.net`):
- `docker.io/library/python:3.12.10-slim` is already cached in the ghost-academy image store (it is the transport's base image)
- `podman run --rm -v gs-vol-{crew_id}:/workspace:ro python:3.12.10-slim ls /workspace` completes in **~200ms**
- Memory footprint of a running worker container: **~614KB**
- Full KiroCrew crew restart (container + gateway): **2–3s**, **~500MB RAM**

## Goals / Non-Goals

**Goals:**
- Evac plain files from stopped crew volumes without waking the crew container
- Evac git bundles and diffs from stopped crew volumes without waking the crew container
- Introduce a reusable `_worker` image for transport-side utility jobs
- Leave the live-container evac path unchanged (no regression)

**Non-Goals:**
- Supply (write) path changes — supply SHALL always target a live container via `_ensure_crew_running`. Writing to a stopped crew's volume without a running container risks consistency issues if the container restarts mid-write. Supply is not in scope for this change.
- Replacing the live-container evac path — sidecar adds latency for already-running containers
- Replacing `_ensure_crew_running` for dispatch/steer — gateway is still required there

## Decisions

### Decision 1: Worker sidecar over fast wake

**Chosen:** Spin up a disposable `_worker` container mounting the crew volume read-only.

**Rejected alternatives:**
- *Fast wake (skip `_wait_gateway`)* — still wakes a full KiroCrew instance (~500MB RAM) just to read a file. Memory-constrained host makes this undesirable.
- *Direct path read via Mountpoint* — volume backing path is not reachable from inside the transport container. Would require bind-mounting the entire storage root into the transport, a large blast radius config change.
- *Volume export API* — streams the entire volume as tar for every read. Acceptable for small idle crews but cost is proportional to workspace size; a seeded repo makes this expensive.

### Decision 2: Single `_worker` image for all stopped-crew file ops

**Chosen:** One `crews/_worker/Containerfile` based on `python:3.12.10-slim` with `git` added.
Tagged `localhost/gs-worker:latest`, built by `install.sh` alongside transport and spec-ops.

This covers both plain file reads (python/cat) and git operations (bundle, diff) in one image.
Since `python:3.12.10-slim` layers are already on disk (shared with the transport image), only
the git layer (~10MB) is additional storage.

**Rejected:** Separate images per use case — unnecessary complexity, same base layers.

### Decision 3: Branching in `_handle_file_get` by container state

**Chosen:** Check `container_is_running` at the top of `_handle_file_get`. Running → existing
path unchanged. Stopped → worker sidecar path.

```
_handle_file_get:
  if container_is_running(crew):
      → existing container_archive_get / container_exec path
  else:
      → worker_read_file(crew_id, path)         # plain file
      → worker_git_bundle(crew_id, path, ref)   # bundle
      → worker_git_diff(crew_id, path, ref)     # diff
```

**Rationale:** Keeps the happy path (running container) zero-cost. Sidecar only activates
when needed. Clean separation — no interleaving of the two paths.

### Decision 4: `_worker` image as general-purpose transport utility

The `_worker` image is not specific to evac. It is the transport's disposable worker unit —
analogous to an SCV or worker unit: cheap, short-lived, does one job and exits. Future
transport-side utility work (inspections, transformations, supply to stopped crews) can reuse
the same image without building a new one.

## Risks / Trade-offs

**[Risk] Worker image not present on first install** → Mitigation: `install.sh` builds
`_worker` as part of the standard build sequence. The transport fails fast with a clear error
if the image is missing.

**[Risk] Worker container left running on error** → Mitigation: always use `--rm`. Wrap
exec in try/finally in `podman.py`. Podman cleans up `--rm` containers even on signal.

**[Risk] Concurrent evac calls spawn multiple workers for same crew** → Acceptable. Workers
mount the volume read-only and are independent. No coordination needed.

**[Risk] Volume written to while worker reads** → Worker mounts `:ro`. If the crew container
is stopped there are no concurrent writers. If the crew restarts mid-read (unlikely — the
branching check was stopped), the read completes against the volume state at open time.

**[Trade-off] ~200ms overhead for stopped-crew reads** → Acceptable. Current path costs
2–3s. Raven background checks are not latency-sensitive.

## Migration Plan

1. Build and tag `localhost/gs-worker:latest` in `install.sh`
2. Add `volume_mount_run` (or equivalent) to `PodmanClient` for the ghost-academy socket
3. Add worker helper functions to `transport/files.py` or a new `transport/worker.py`
4. Branch `_handle_file_get` by container state
5. No data migration needed — volume format is unchanged
6. Rollback: remove the branch, revert to unconditional `_ensure_crew_running`

## Supply path (explicit decision)

Supply always goes to a **live container** via `_ensure_crew_running`, unchanged. There is
no stopped-crew write path. Rationale: writing to a volume while the owning container may
restart creates consistency risk (partial writes, git index corruption). The evac/supply
asymmetry is intentional — reads are safe at any time, writes require the container to be up
and owning the filesystem.
