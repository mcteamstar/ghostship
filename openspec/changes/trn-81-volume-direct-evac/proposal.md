# TRN-81 — Volume-direct evac for stopped crews

## Status

**Investigation required before design.** The core approach (Podman volume
export API) crosses the isolation boundary between the ghostship transport and
the crew container. The design implications of that boundary crossing need to
be understood and decided before any implementation begins. This proposal
documents the problem and frames the investigation — it is not a ready-to-implement spec.

## Problem

Every `evac` and `supply` call requires the crew container to be running.
`_ensure_crew_running` (called unconditionally at the top of `_handle_file_get`
and `_handle_file_post`) will restart a stopped container transparently, but
this has real costs:

- **~2–3s latency** just to start the gateway before any file operation begins
- **Total failure** if the container won't start — broken image, OOM, or
  corrupt state means all workspace data becomes inaccessible with no rescue path
- **Unnecessary wake** for the common case of reading a single file from an
  idle crew — wakes the container, resets the idle timer, keeps the crew running
  longer

TRN-51 specifically needs to read mailbox subject lines from stopped crews
without waking them.

## Candidate approach

The Podman REST API exposes `GET /libpod/volumes/{name}/export` which streams
the full volume as a tar without a running container. The transport could use
this to read files directly from the crew's workspace volume.

## The isolation boundary problem

**This is the central design question.** The ghostship architecture deliberately
maintains an isolation boundary between the transport and the crew container:
the transport orchestrates containers but does not reach inside them directly
for data. The current file-read path (container exec → tar stream) respects
this — it talks to the running container, which owns its own filesystem.

Volume-direct access breaks this model: the transport would reach directly into
a volume that the crew container owns, bypassing the container entirely. This
raises several design questions that need answers before the approach can be
adopted:

1. **Consistency** — is it safe to read from a volume while its owning
   container is stopped? Podman volumes are not copy-on-write; a stopped
   container's volume reflects the last committed state. Is that the right
   semantics for evac? What if the container is mid-write when stopped?

2. **Security** — the transport container (`ga-transport`) reading the crew's
   volume directly means the transport can access any file in the crew's
   workspace, including secrets (`.admiral_secret`, auth tokens, kiro DB).
   Currently the transport only reads what the container explicitly shells out
   via exec. Volume-direct removes that exec boundary. Is this acceptable given
   the single-operator threat model?

3. **Container image dependency** — the current exec path requires `git` to
   be installed in the *crew* container (for bundle/diff). Volume-direct for
   git operations would require `git` in the *transport* container, which
   currently has no git. Does the Containerfile need to change?

4. **Volume naming and access** — the workspace volume is named
   `gs-vol-{crew_id}`. The transport already knows this name (used at nuke
   time). Is it acceptable for the transport to export volumes by name
   outside of the nuke flow? Or should volume access be gated more narrowly?

5. **Alternative: a lightweight sidecar** — instead of direct volume export,
   could a minimal sidecar container (no gateway, just busybox + git) be spun
   up against the same volume for file reads? This preserves the
   container-mediated access model while eliminating gateway startup latency.
   Trade-off: complexity of managing a sidecar lifecycle.

6. **Alternative: keep restart, make it faster** — the 2–3s latency is
   gateway startup time. Could `_ensure_crew_running` skip the full
   `_wait_gateway` for a "read-only wake" that just starts the container
   without waiting for the gateway? The container filesystem is accessible via
   exec even before the gateway is healthy.

## Investigation required

Before a design can be committed to, the following need to be answered —
ideally by a Wraith on a live crew:

1. Does `GET /libpod/volumes/{name}/export` work reliably in rootless mode
   on a representative test host? Test against a stopped crew volume.
2. Is streaming tar extraction of a specific file practical without full
   buffering? (`tarfile.open(mode="r|", fileobj=stream)`)
3. What is the security posture of volume-direct access in the single-operator
   model — is the exec boundary worth preserving?
4. Is the sidecar approach viable and simpler than volume export?
5. What is the actual latency of `_ensure_crew_running` for a stopped crew —
   is the 2–3s estimate accurate on a representative test host, and is it
   worth the architectural complexity to eliminate?

## Expected outcome

Either:
- A revised proposal with a chosen approach (volume export, sidecar, or fast
  restart), a clear decision on the isolation boundary, and concrete design
  and tasks; or
- A documented decision that the restart path is acceptable with latency
  improvements (fast wake), deferring the boundary-crossing question.

## Files likely affected

| File | Change |
|:-----|:-------|
| `transport/podman.py` | New volume read method (if volume export approach chosen) |
| `transport/files.py` | Branching logic in `_handle_file_get` |
| `transport/lifecycle.py` | Possibly: fast-wake variant of `_ensure_crew_running` |
| `crews/_base/Containerfile` or transport `Containerfile` | If git needed transport-side |

## Dependencies

This is a prerequisite for TRN-51.
