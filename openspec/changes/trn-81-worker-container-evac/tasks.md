## 1. Worker image

- [x] 1.1 Create `crews/_worker/Containerfile` — `FROM python:3.12.10-slim`, install `git` via apt, no other additions
- [x] 1.2 Add `_worker` image build step to `install.sh` (tag `localhost/gs-worker:latest`), positioned after `_base` and before crew compositions
- [ ] 1.3 Verify `localhost/gs-worker:latest` is present after `./install.sh` on the academy VM

## 2. PodmanClient — worker run support

- [x] 2.1 Add `worker_run(volume_name, cmd, timeout)` method to `PodmanClient` in `transport/podman.py` — runs `podman run --rm -v {volume}:/workspace:ro localhost/gs-worker:latest {cmd}`, returns stdout as string
- [x] 2.2 Ensure `worker_run` cleans up the container on both success and error (rely on `--rm`; wrap in try/finally if needed)
- [x] 2.3 Add `volume_name_for_crew(crew_id)` helper (returns `gs-vol-{crew_id}`) — or inline where used

## 3. Worker file-read helpers

- [x] 3.1 Add `worker_read_file(podman, crew_id, path)` in `transport/files.py` — calls `worker_run` with `cat /workspace/{path}`, returns bytes
- [x] 3.2 Add `worker_git_bundle(podman, crew_id, repo_path, ref)` — calls `worker_run` with `git -C /workspace/{repo_path} bundle create - {ref}`, returns bytes
- [x] 3.3 Add `worker_git_diff(podman, crew_id, repo_path, ref)` — calls `worker_run` with `git -C /workspace/{repo_path} diff {ref}`, returns string

## 4. Supply path — no change

Supply (`_handle_file_put`) always requires a live container. No changes to the supply path.
`_ensure_crew_running` continues to be called unconditionally for all supply requests.

## 5. Branch `_handle_file_get` by container state

- [x] 5.1 In `_handle_file_get`, check `podman.container_is_running(crew["container"])` before the existing `_ensure_crew_running` call
- [x] 5.2 Running container → existing path unchanged (no behaviour change)
- [x] 5.3 Stopped container, plain file → `worker_read_file`; stream result as `StreamingResponse`
- [x] 5.4 Stopped container, `?bundle=1` → `worker_git_bundle`; stream result
- [x] 5.5 Stopped container, `?ref=<ref>` (diff) → `worker_git_diff`; return as `PlainTextResponse`
- [x] 5.6 Stopped container path must NOT call `_touch_crew` (do not update idle timestamp)

## 6. Error handling

- [x] 6.1 File not found in worker (cat exits non-zero) → return HTTP 404 with clear message
- [x] 6.2 `localhost/gs-worker:latest` image missing → return HTTP 500 naming the missing image
- [x] 6.3 Worker container fails to start → return HTTP 500, log the error
- [x] 6.4 Git operation fails in worker (not a git repo, ref not found) → return HTTP 500 with git stderr

## 7. Tests

- [x] 7.1 Unit test `worker_read_file` with a mock `PodmanClient` — happy path returns file bytes
- [x] 7.2 Unit test `worker_read_file` — file not found raises / returns correct error
- [x] 7.3 Unit test `_handle_file_get` branching — stopped crew routes to worker helpers, running crew routes to existing path
- [ ] 7.4 Integration test on academy VM: evac a plain file from a stopped crew via the new path; assert crew container remains stopped after the call
