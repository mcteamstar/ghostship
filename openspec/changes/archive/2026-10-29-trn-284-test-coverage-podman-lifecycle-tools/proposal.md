# Proposal

## Why

The indy-0.10.0 review found three CRITICAL coverage gaps (C-1/C-2/C-3) and four
HIGH gaps (H-4/H-5/H-6/H-7) in the transport layer. The three critical modules —
`podman.py` (24%), `lifecycle.py` (28%), `tools.py` (37%) — are the core runtime
surface: they handle all container operations, the crew state machine, and the entire
MCP API. Silent failure paths in these files are the most likely sources of production
incidents.

The indy-0.9.1 cycle raised test count from 975 to 1132. This change targets the
next layer of coverage debt with the highest risk-to-effort ratio.

## What Changes

### C-1 — `transport/podman.py`: add `test_podman.py` (currently 24%)

PodmanClient has virtually no unit tests. All container/network/volume/secret/worker
operations are exercised only indirectly via e2e tests. Add `test_podman.py`
exercising PodmanClient against a mock Unix socket (socketpair or patch) and verify
`FakePodmanClient` interface parity with the real client.

Priority paths: `container_create`, `container_exec_stdin`, `container_archive_put/get`,
`network_create/connect/disconnect`, `volume_create/remove`, error handling (HTTP 500,
malformed response, socket closed).

### C-2 — `transport/lifecycle.py`: extend `test_lifecycle.py` (currently 28%)

Key untested paths (below 50% or 0%): `_reconcile_registry`, `_reseed_crew_schedules`,
`_dispatch_batch/_pickup_single`, `_poll_round`, `_process_collected`, `_mint_cookie`,
`_refresh_cookie`, `_prewarm_crew`, `_patch_crew_config`, `_wait_gateway`,
`_inject_auth`, `_read_auth_from_crew`, `_copy_agents/_copy_skills/_copy_steering`.

Focus first on `_reconcile_registry` and `_reseed_crew_schedules` as they are the
most complex and most likely to regress after the H-1/H-2 fixes in TRN-283.

### C-3 — `transport/tools.py`: add `test_tools.py` (currently 37%)

No dedicated `test_tools.py` exists. Add it covering: `nuke()` confirm=True/False
branches, `schedule()` validation (missing name, invalid interval, cancel non-existent
job), `dispatch()` error paths (crew not found, gateway unreachable), `_schedule_cancel`,
`resource_agents`, `resource_jobs`, `supply/evac/pickup` error branches.

### H-4 — `transport/captain_engine.py`: extend `test_captain_engine.py` (currently 34%)

Current 13 tests cover the surface; core dispatch/steer paths are untested. Add:
`_dispatch_captain_checkin` (memory pressure skip, model override for claude backend),
`_steer_captain_checkin` (400 continue branch, non-400 error), `_captain_do_order`
(interval vs cron, re-order existing), `_record_memory_pressure_cycle` (escalation
boundary).

### H-5 — `transport/server.py`: UI/WS/API proxy coverage (currently 43%)

UI proxy cookie-refresh path, WebSocket relay, and crew API proxy handlers all at 0%.
Add stub tests for proxy routing, cookie injection, and 404/500 error paths.

### H-6 — `transport/files.py`: upload and git paths (currently 40%)

`_transfer_upload` (69 lines, 0%), `worker_read_file/worker_git_bundle/worker_git_diff`
(0%), `_handle_file_get/_handle_upload_put` (0%). Add tests for upload path including
the git-clone fallback and path-traversal rejection.

### H-7 — `transport/academy.py`: composition registry error paths (currently 51%)

`_load_composition_registry` error branches, `_load_crew_manifest` JSON parse failure,
`AcademyLoader._stage_mcp` env-var substitution, `_run_setup`, `_copy_agents`.

## Capabilities

### Modified Capabilities

- `transport-test-coverage`: New test files and extended existing ones for the seven
  gaps above. No runtime behaviour changes — tests only.

## Impact

- `tests/unit/test_podman.py` — new
- `tests/unit/test_tools.py` — new
- `tests/unit/test_lifecycle.py` — major extension
- `tests/unit/test_captain_engine.py` — extension
- `tests/unit/test_server.py` — extension
- `tests/unit/test_files.py` — extension (upload/git paths)
- `tests/unit/test_academy.py` — extension
- `tests/unit/conftest.py` — likely new FakePodmanClient socket helpers
