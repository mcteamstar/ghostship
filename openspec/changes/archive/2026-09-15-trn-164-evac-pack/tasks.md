## 1. MCP Tool

- [ ] 1.1 Add `pack: bool = False` parameter to `evac()` in `transport/server.py`
- [ ] 1.2 Add mutual-exclusion guard: return error if both `pack=True` and `bundle=True`
- [ ] 1.3 Pass `pack` to `_sign_file_url` and include it in the returned result dict
- [ ] 1.4 Update the `evac` tool docstring to document the `pack` parameter

## 2. URL Signing and Verification

- [ ] 2.1 Extend `_sign_file_url` in `transport/files.py` to accept `pack: bool = False` and include it in the sorted GET flags set (alongside `bundle`)
- [ ] 2.2 Extend `_verify_file_token` to accept `pack: bool = False` and verify the flag in the GET path payload reconstruction
- [ ] 2.3 Add `&pack=1` to the generated URL when `pack=True`

## 3. HTTP Handler — Running Crew

- [ ] 3.1 Parse `?pack=1` from query params in `_handle_file_get`
- [ ] 3.2 Pass `pack` to `_verify_file_token`
- [ ] 3.3 Add the `pack` branch in the running-crew path: call `container_archive_get(container, path)` and stream the raw response bytes as `application/x-tar` (skip `_TarMemberStream` unwrapping)

## 4. HTTP Handler — Stopped Crew

- [ ] 4.1 Add `worker_tar_dir(podman, crew_id, path)` function in `transport/files.py` that runs `tar -cf - <path>` in the worker sidecar and returns the bytes
- [ ] 4.2 Add the `pack` branch in the stopped-crew path: call `worker_tar_dir` and return the bytes as `application/x-tar`

## 5. Tests

- [ ] 5.1 Unit test: `evac(pack=True, bundle=True)` returns an error, no URL issued
- [ ] 5.2 Unit test: `_sign_file_url` with `pack=True` includes `pack` in the flags string
- [ ] 5.3 Unit test: `_verify_file_token` rejects a plain-file token replayed with `?pack=1`
- [ ] 5.4 Unit test: `_handle_file_get` with `?pack=1` on a running crew streams raw Podman archive bytes with `Content-Type: application/x-tar`
- [ ] 5.5 Unit test: `_handle_file_get` with `?pack=1` on a stopped crew calls `worker_tar_dir` and streams the result
- [ ] 5.6 Unit test: `worker_tar_dir` calls the worker sidecar with the correct `tar -czf -` command
