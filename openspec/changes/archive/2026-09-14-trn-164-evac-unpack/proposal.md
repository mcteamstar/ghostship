# TRN-164: evac unpack — directory tree extraction from crew workspaces

## Why

`supply(unpack=True)` lets a caller push a directory tree (tar/tar.gz) into a
crew workspace, but there is no symmetric mode on `evac` to pull a directory
tree back out. Callers who want to extract multi-file output (e.g. a generated
reports directory, a build artefact tree, or the entire `subagent_*/` working
directory) must enumerate and download files one by one, or work around the gap
by manually creating a tar inside the crew before evacuating it as a plain file.
Adding `evac(unpack=True)` closes this asymmetry and makes the supply/evac pair
a complete bidirectional file-exchange protocol.

## What Changes

- New `unpack: bool = False` parameter on the `evac()` MCP tool. When `True`,
  the presigned download URL returns the target **directory** as a raw tar
  archive (the Podman archive-GET response passed through directly), instead of
  streaming a single file.
- `unpack` and `bundle` are mutually exclusive on `evac` (matching the existing
  constraint on `supply`). Passing both returns an error without issuing a URL.
- `_sign_file_url` includes the `unpack` flag in its HMAC payload (alongside the
  existing `bundle` flag) so a token signed for a single-file download cannot be
  replayed as a directory extraction.
- `_verify_file_token` enforces the `unpack` flag on GET requests: a token
  signed without `unpack` is rejected if the request carries `?unpack=1`, and
  vice versa.
- `_handle_file_get` passes the raw Podman tar stream through to the caller when
  `unpack=1` is present and verified, instead of peeling a single member via
  `_TarMemberStream`.
- The stopped-crew path (worker sidecar) gains the same `unpack` mode: directory
  extraction from a stopped crew uses the Podman archive API directly (the same
  approach as stopped-crew plain-file evac today), wrapped in a streaming
  response.
- The `evac()` docstring and curl example updated to document the new mode.

## Capabilities

### New Capabilities

None — this change extends an existing capability.

### Modified Capabilities

- `file-transfer`: New `unpack` mode on evac (GET path). `_sign_file_url` and
  `_verify_file_token` updated to cover the `unpack` flag in the HMAC payload.
  Mutual-exclusion constraint (`unpack` + `bundle`) added to `evac` mirroring
  the existing constraint on `supply`.

## Impact

- `transport/server.py`: `evac()` gains `unpack: bool = False`; mutual-exclusion
  guard; `_sign_file_url` call updated to pass `unpack`.
- `transport/files.py`: `_sign_file_url` includes `unpack` in flags; `_verify_file_token`
  verifies `unpack` on GET path; `_handle_file_get` adds `unpack` branch (raw
  tar passthrough, both running and stopped-crew paths).
- `tests/unit/test_file_transfer.py` and `tests/unit/test_server.py`: new tests
  for the `unpack` mode on evac (URL signing, token verification, handler).
- No dependency changes. No breaking changes to existing `evac` callers (default
  `unpack=False` preserves current behaviour exactly).
