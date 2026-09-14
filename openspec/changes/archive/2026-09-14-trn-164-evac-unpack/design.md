# Design: evac unpack

## Context

See `proposal.md` — Why, for motivation.

`evac` today works in three modes, selected by query parameters on the presigned
GET URL:

| mode | params | implementation |
|---|---|---|
| plain file | (none) | `_TarMemberStream` peels one member from Podman archive-GET tar |
| git diff | `?ref=<ref>` | `container_exec git diff` |
| git bundle | `?bundle=1` | `container_exec git bundle create` then `container_archive_get` |

`supply` already supports `unpack=True` (directory tree via tar POST). There is
no symmetric GET path. The Podman archive-GET endpoint natively returns a tar
stream for any path, file or directory — the current `_TarMemberStream` layer is
specifically what unwraps it to a single file. The new mode simply skips that
unwrap.

The HMAC payload for GET tokens is currently:

```
{crew_id}:{path}:{expires}:GET:{ref or ''}:{flags}
```

where `flags` is a sorted colon-joined set — currently only `bundle` participates.
Adding `unpack` to `flags` is the minimal change to include it in the signed
payload.

## Goals / Non-Goals

**Goals:**
- Add `unpack=True` to `evac()` MCP tool: returns a presigned URL whose response is the raw Podman tar for a directory.
- Include `unpack` in the GET HMAC payload so a plain-file token cannot be replayed as an unpack request.
- Cover both running-crew and stopped-crew paths.
- No changes to the happy-path `supply` code.

**Non-Goals:**
- Streaming a tar.gz (compressed) response — Podman archive-GET produces uncompressed tar; the caller can pipe through `gzip` if needed.
- Adding `unpack` to `_sign_upload_url` / `_verify_file_token` POST path — `unpack` is already there for uploads (added in TRN-38).
- Filtering or transforming the tar member list before streaming.
- Any UI or dashboard changes.

## Decisions

### 1. Skip `_TarMemberStream` entirely on the unpack path

**Decision**: When `unpack=True`, return a `StreamingResponse` over the raw
`container_archive_get` response bytes, bypassing `_TarMemberStream`.

**Rationale**: `_TarMemberStream` exists solely to peel a single regular-file
member from the Podman archive response. For directory evac we want the full tar,
so the class is an obstacle, not a tool. Bypassing it is the smallest change and
adds no new abstraction.

**Alternative considered**: Extend `_TarMemberStream` with a "passthrough" mode
that re-emits all members. Rejected — complicates the class for a case that does
not need it at all.

### 2. Add `unpack` to the GET HMAC `flags` field

**Decision**: `_sign_file_url` constructs `flags` from both `bundle` and `unpack`.
`_verify_file_token` reconstructs the same flags for GET paths and includes
`unpack` in the comparison.

**Rationale**: The existing `_verify_file_token` already handles a `mode`
parameter for POST (upload) tokens with exactly this approach — sorted flag set
in the payload. Applying the same pattern to GET tokens is consistent and minimal.

**Alternative considered**: A separate `unpack`-specific URL path / endpoint.
Rejected — introduces a new route that duplicates the token and crew-lookup logic
already in `_handle_file_get`, for no benefit.

### 3. Stopped-crew path: use `container_archive_get` directly

**Decision**: For stopped crews with `unpack=True`, call `container_archive_get`
on the crew container path and stream the response directly, the same way
stopped-crew plain-file evac already works. Do not spawn a worker container.

**Rationale**: The Podman archive API operates on both running and stopped
containers via the overlay filesystem. The worker sidecar (`worker_git_bundle`,
`worker_git_diff`) exists only for operations that require a running git process.
A directory tar requires no git process, so the lighter direct path applies.

### 4. Mutual exclusion enforced at the `evac()` MCP tool level, not the HTTP handler

**Decision**: `evac()` in `server.py` rejects `unpack=True, bundle=True` before
calling `_sign_file_url`. The HTTP handler does not receive URLs with both flags
set.

**Rationale**: Matches the existing `supply()` pattern, which also rejects the
conflict before signing. Keeps the signing and verification logic simpler by
ensuring the flags set is always valid.

## Risks / Trade-offs

- **Large directory tars can be slow to stream**: Podman archive-GET is
  streaming but not rate-limited. A caller evacuating a very large directory
  holds the presigned URL open for the full stream duration (up to 300 s TTL).
  Mitigation: callers should evac specific subdirectories (e.g. `subagent_*/`)
  rather than the whole workspace root. No change needed now; document in the
  `evac()` docstring.

- **Tar member order is determined by Podman/overlayfs**: The caller receives
  whatever order the underlying filesystem presents. This is the same contract
  as supply's unpack output — callers cannot rely on ordering. No mitigation
  needed.

- **No Content-Length header**: Streaming a live tar means the server cannot
  know the total size in advance. This is already the case for git-bundle evac
  and is an accepted constraint of the streaming architecture.

## Migration Plan

No data migration required. The new `unpack` parameter defaults to `False`,
preserving all existing evac behaviour. Deployment is a straightforward in-place
update of `transport/server.py` and `transport/files.py`.

## Open Questions

None. All material decisions are resolved above.
