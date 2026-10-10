# Proposal

Source: independent review of `release/0.6.0` at `ee0b3b8` (2026-10-09), run on the Claude backend. Reviewers: **S** security, **Q** quality, **T** test coverage, **D** docs. "Reproduced" means the reviewer or a live check ran code to confirm it; everything else is from reading the code and needs confirming during assessment. Target: a release after 0.6.0.

Full reviewer reports: crew `ghostship-indy-060` tasks `169e9101b28e91e4` (security), `d615d73e3b7c9e37` (quality), `408dea89af5f6789` (test coverage), `45df3b672a262c4c` (docs) — retrieve with `pickup(task_id, crew_id)` while the crew exists. Line numbers refer to `ee0b3b8` and may drift. Next step for whoever picks this up: work through **Assess first**, then write specs, design and tasks with `openspec instructions <artifact> --change <name>`.

## Why

The unit suite passes (1210 at review time) but several high-risk paths are untested, tested against copies of the code, or only reached through mocks.

## Findings

| Severity | Finding | Where | Who | Status |
|---|---|---|---|---|
| High | Install and uninstall shell tests reimplement the scripts and have drifted (accept flags `install.sh` doesn't have, miss ones it does). The uninstall credential-preservation test would pass if `uninstall.sh` deleted credentials. | `tests/integration/test_install_config.sh:32`, `:196`; `test_uninstall_auth_preservation.sh:26` | T | Reproduced (drift) |
| High | Codex login internals have no direct tests; every server test patches the poll (this hid the false-completion bug). | `lifecycle.py:2767-3050`; `test_trn172_codex_backend.py:538` | T | Reproduced |
| Medium | CI runs only `--unit`; integration tests run only by hand. | `.github/workflows/test.yml` | T | Read only |
| Medium | Shared PTY helper tested only with no prompts and no code pattern; `container_exec_pty_stdin` only ever mocked. | `lifecycle.py:2220-2321`; `podman.py:360` | T | Read only |
| Medium | Claude auth write and inject (0600 mode, chunk reassembly), Podman stdin and worker paths, the WebSocket proxy, `setup.py` and `start.sh` largely untested. | various | T | Coverage measured |
| Medium | Dashboard relay tests mirror the relay logic instead of calling it (rewritten in TRN-202). | `test_dashboard_session.py` `WsRelayEventDispatchTests` | prior review | Known |
| Low | Argon2 path dead in CI (dependency undeclared); `get_secret` env fallback untested; coverage is line-only. | `security.py:77-267` | T | Read only |
| Gap | No e2e coverage of the Claude or Codex login (both need a person to paste or approve). | `tests/e2e` | T, live | Known |

## Assess first

- Decide whether integration tests join CI, and how to run the real `install.sh` in a sandbox (stub `podman` on `PATH`, sandboxed `HOME`).

## What Changes

- Run the real install/uninstall scripts in a sandbox; add `--integration` to CI.
- Direct tests for the Codex login, the PTY helper (socketpair), auth write/inject, and the WebSocket relay closure.
- Branch coverage for `transport/`.

## Capabilities

### New Capabilities

- None expected.

### Modified Capabilities

- `test-orchestration`, `transport-test-coverage`.

## Impact

`tests/`, `.github/workflows/test.yml`. No production code, except possibly extracting the WebSocket relay closure so it can be tested.
