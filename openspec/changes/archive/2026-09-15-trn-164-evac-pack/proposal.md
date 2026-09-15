## Why

`supply` accepts `unpack=True` to inject a tar archive and extract it into the workspace, but `evac` has no equivalent — callers can only pull a single file, a git diff, or a git bundle. Extracting a directory tree (e.g. generated output, a report folder, or any non-git subtree) currently requires either using a git bundle (coupling the caller to git) or pulling files one by one. Adding `pack=True` to `evac` closes this asymmetry and makes the supply/evac pair a true two-way file exchange protocol.

## What Changes

- `evac` MCP tool gains a `pack: bool = False` parameter. When `True`, the presigned URL streams a tar archive of the requested directory rather than a single file.
- `_sign_file_url` and `_verify_file_token` include `pack` in the GET signed payload flags, preventing a token signed for a plain file from being replayed as a tar-out request.
- `_handle_file_get` gains a `?pack=1` branch. For a running crew it streams the raw Podman archive response (already tar format) directly instead of unwrapping it via `_TarMemberStream`. For a stopped crew it uses the worker sidecar via a new `worker_tar_dir` helper.
- New `worker_tar_dir(podman, crew_id, path)` function in `files.py` runs `tar -cf - <path>` inside the worker container and returns the bytes.
- Tests cover the new mode: MCP tool validation, URL signing/verification, running-crew streaming, stopped-crew worker path, and token replay rejection.

## Capabilities

### New Capabilities

_(none — this extends existing behaviour)_

### Modified Capabilities

- `file-transfer`: The `evac` tool gains a new `pack` mode. The presigned URL signing scheme for GET URLs is extended to include the `pack` flag. The stopped-crew worker path gains a tar-directory extraction function. Existing evac scenarios are unaffected.

## Impact

- `transport/files.py`: `_sign_file_url`, `_verify_file_token`, `_handle_file_get`, new `worker_tar_dir`
- `transport/server.py`: `evac` tool signature and docstring
- `tests/unit/test_files.py` and/or `test_file_transfer.py`: new test cases
- No API breaking changes — `pack` defaults to `False` and existing evac URLs are unaffected
- The HMAC payload format for GET URLs changes (adds the `pack` flag); existing signed URLs remain valid because `pack=False` produces an empty flags string, which is what current tokens sign over
