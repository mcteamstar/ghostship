## Context

See proposal.md — Why for motivation.

The transport's file GET handler (`_handle_file_get` in `files.py`) currently dispatches to one of three modes based on query params:

- `?bundle=1` → git bundle via `container_archive_get` + temp file + `_TarMemberStream` unwrap, or via `worker_git_bundle` on stopped crews
- `?ref=<ref>` (no bundle) → git diff via `container_exec` or `worker_git_diff`
- neither → single file via `container_archive_get` + `_TarMemberStream` unwrap, or `worker_read_file` on stopped crews

Crucially, Podman's `container_archive_get` already returns a raw tar stream. The plain-file path unwraps it (`_TarMemberStream`) to stream just the single file member. For directory evac, the unwrap must be skipped and the raw Podman tar streamed directly.

The HMAC signing for GET URLs currently flags only `bundle`. Adding `pack` means the flags set grows to `{bundle, pack}`, sorted before joining (same pattern as the upload side's `{bundle, force, unpack}`). Existing signed tokens remain valid: when both flags are false the flags string is `""`, which is what current tokens sign over.

## Goals / Non-Goals

**Goals:**
- `evac(pack=True)` returns a presigned URL that streams a tar archive of the named directory
- Running-crew path: stream raw Podman archive response (no `_TarMemberStream` unwrap)
- Stopped-crew path: new `worker_tar_dir` helper runs `tar -czf - <path>` in the worker sidecar
- `pack` is included in the HMAC flags for GET URLs — replay of a file URL as a pack request is rejected 403
- `pack` and `bundle` are mutually exclusive — both=True returns an error, no URL issued
- Backward compatible: `pack` defaults to `False`, existing tokens and callers unaffected

**Non-Goals:**
- Filtering or selective extraction of tar members (caller receives the full tree)
- Compression format negotiation (tar is sufficient; gzip is optional)
- Writing a `worker_untar_dir` (that's supply's job, not evac)

## Decisions

### D1: Stream raw Podman archive for running crews (skip _TarMemberStream)

`container_archive_get(container, path)` returns an `httpx.Response` whose body is already a valid tar stream. For a directory path, Podman naturally returns a multi-member tar. For the pack case we just stream the response bytes directly as `application/x-tar` — no unwrapping, no temp file, no intermediate buffer.

Alternative considered: run `tar -czf -` via `container_exec` and stream stdout. Rejected — Podman's archive API is the correct primitive for this and avoids an extra exec round-trip.

### D2: worker_tar_dir for stopped crews

The stopped-crew path can't use `container_archive_get` directly without starting the container (that would defeat the point). The existing pattern for stopped crews is to spin up a short-lived worker sidecar that mounts the volume read-only. `worker_read_file` uses `cat`; the new `worker_tar_dir` runs `tar -cf - <path>` (plain tar, no compression — consistent with Podman's native `container_archive_get` output) and returns the bytes. This keeps the stopped-crew pattern consistent and avoids a compression mismatch between the two paths.

Alternative considered: use `tar -czf -` (gzip) in the worker. Rejected — Podman's `container_archive_get` returns plain tar, so using gzip only in the worker path would produce different archive formats depending on whether the crew is running or stopped. Plain tar is consistent throughout.

### D3: HMAC flag inclusion — extend the sorted flags set

The GET URL signing already uses a sorted `":"` -joined flags string. Adding `pack` to the set `{bundle, pack}` is backward compatible: absent flags contribute nothing to the string, so `bundle=False, pack=False` → `""` as before.

Alternative considered: a separate signing function for pack URLs. Rejected — the unified flag approach is already established for upload URLs and keeps the verification logic in one place.

### D4: Mutual exclusion of pack and bundle at the MCP tool layer

`evac(pack=True, bundle=True)` is rejected before a URL is issued, matching the supply-side `unpack + bundle` guard. No HTTP-layer guard is needed since the URL can't be signed with both flags true.

## Risks / Trade-offs

- [Risk] Large directories produce large tars that must stream through the transport. Mitigation: the response is streamed (not buffered), same as bundle mode. No size limit is introduced — callers should be mindful of workspace size. Plain tar (no compression) is used throughout for consistency with Podman's native archive format; callers can pipe through `gzip` locally if compression is needed.
- [Risk] The `container_archive_get` Podman API path produces a tar whose root member name is implementation-defined (Podman typically uses the basename of the requested path). Callers need to be aware when extracting. Mitigation: document in the tool docstring that the tar is a raw Podman archive.
- [Risk] Stopped-crew `worker_tar_dir` adds a new `tar` invocation inside the worker image. The worker image (`_worker/Containerfile`) must have `tar` available. It's a standard util — present in all tested base images. No Containerfile change needed.

## Migration Plan

No migration required. The change is purely additive:
- `pack` defaults to `False` — existing evac calls are unaffected
- Existing signed GET URLs remain valid (empty flags string unchanged)
- No database, volume, or registry schema changes
