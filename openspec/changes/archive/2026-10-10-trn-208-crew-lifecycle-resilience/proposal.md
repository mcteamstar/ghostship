# Proposal

Source: independent review of `release/0.6.0` at `ee0b3b8` (2026-10-09), run on the Claude backend. Reviewers: **S** security, **Q** quality, **T** test coverage, **D** docs. "Reproduced" means the reviewer or a live check ran code to confirm it; everything else is from reading the code and needs confirming during assessment. Target: a release after 0.6.0.

Full reviewer reports: crew `ghostship-indy-060` tasks `169e9101b28e91e4` (security), `d615d73e3b7c9e37` (quality), `408dea89af5f6789` (test coverage), `45df3b672a262c4c` (docs) — retrieve with `pickup(task_id, crew_id)` while the crew exists. Line numbers refer to `ee0b3b8` and may drift. Next step for whoever picks this up: work through **Assess first**, then write specs, design and tasks with `openspec instructions <artifact> --change <name>`.

## Why

Crew recovery, the registry and the idle reaper fail in ways that hang crews, lose registry data or leave crews running. Most are pre-existing; the recovery deadlock path is new with member enrolment (TRN-186) in 0.6.0.

## Findings

| Severity | Finding | Where | Who | Status |
|---|---|---|---|---|
| Critical | Recovery self-deadlock: `_enroll_crew_members` calls `_crew_api_with_recovery` while the same non-reentrant per-crew lock is held. Later calls to that crew wait and fail until the transport restarts. | `lifecycle.py:537`, `:786`, `:1686` | Q | Reproduced in a stubbed harness. **Not** reproduced on the idle-wake path: a live stop-then-dispatch restarted the crew in 13s. Likely needs a dead gateway inside a running container. |
| High | A registry read error (EACCES, EIO, invalid UTF-8) returns an empty registry; the next launch saves it and every other crew is lost. | `registry.py:62`; `server.py:2428` | Q | Reproduced (read path) |
| Medium | Idle reaper decides from a registry snapshot taken before its HTTP checks and doesn't re-check `last_used` before stopping, so a crew touched during the checks can still be stopped. | `monitors.py:379-507` | Q | Read only |
| High | Transient Podman errors read as "gone" or "not running": `container_exists` and `container_is_running` return False on any non-200, so startup can drop registry entries and healthy crews get restarted. | `podman.py:297-304`; `lifecycle.py:1425`, `:605` | Q | Read only |
| High | A concurrent caller can stop a crew that another thread is restarting (probe-then-stop runs before leader election). | `lifecycle.py:605-629` | Q | Read only |
| Medium | Non-idempotent POSTs (task dispatch) are retried after a connection reset. | `lifecycle.py:421`, `:477`, `:501` | Q | Read only |
| Medium | Leaks on error paths: login container created but not removed when start fails; crew left running while registry says stopped; admiral secret file left after a failed launch. | `lifecycle.py:1984`, `:765`; `server.py:2592` | Q | Read only |
| Medium | Blocking Podman I/O inside async handlers, and `_registry_lock` taken on the event-loop thread while other threads hold it across I/O. | `server.py:1600`, `:1804`, `:1083`, `:1186`, `:1042` | Q | Read only |
| Medium | Captain order lock evicted on nuke while a running order may hold it. | `server.py:2945` | Q | Read only |
| Observed | Idle reaper stopped neither crew after 38 and 27 minutes idle (`GA_IDLE_TIMEOUT_SECS=300`). No traceback. Could be fail-open on a check error or a KiroCrew 0.8.0 default cron counting as "enabled". The reaper now logs why it keeps each crew running (`Idle crew <id> kept running: <reason>`), so the transport log should answer this. | `monitors.py:361` | live check | Unexplained |
| Low | Restart enrolment now tries KiroCrew 0.8.0's built-in agents (`kirocrew`, `kirocrew-lite`, …) and logs six 404 warnings per restart. | `lifecycle.py` `_enroll_crew_members` | live check | Reproduced |

## Assess first

- Reproduce the deadlock against a real crew: kill the gateway process inside a running crew (not the container) and call the crew.
- Find out why the idle reaper isn't stopping crews on 0.8.0: read the `kept running` log lines, and check whether 0.8.0 seeds cron jobs.
- Decide the enrolment filter: only the composition's personas, not every agent JSON in the image.

## What Changes

- Enrolment uses `_crew_api` with its own error handling, never the recovery wrapper.
- Registry: empty structure only when the file is missing; other errors fail the request.
- Reaper: re-check `last_used` under the lock immediately before stopping.
- Podman helpers: False only on 404, raise otherwise; skip registry removal when the check failed.
- Restart: check `_startup_events` before probe-and-stop.
- Retry only idempotent methods; clean up on the listed error paths; move blocking calls to `asyncio.to_thread`.

## Capabilities

### New Capabilities

- None expected.

### Modified Capabilities

- `idle-and-recovery`: recovery must not re-enter its own lock; reaper re-checks activity before stopping.
- `registry/durability`: read errors never become an empty registry.
- `crew-lifecycle`: Podman error semantics, restart coordination, enrolment scope.

## Impact

`transport/lifecycle.py`, `transport/registry.py`, `transport/monitors.py`, `transport/podman.py`, `transport/server.py`. Unit tests for each path; the deadlock needs a lock-re-entry test.
