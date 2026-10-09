# Proposal

Source: independent review of `release/0.6.0` at `ee0b3b8` (2026-10-09), run on the Claude backend. Reviewers: **S** security, **Q** quality, **T** test coverage, **D** docs. "Reproduced" means the reviewer or a live check ran code to confirm it; everything else is from reading the code and needs confirming during assessment. Target: a release after 0.6.0.

Full reviewer reports: crew `ghostship-indy-060` tasks `169e9101b28e91e4` (security), `d615d73e3b7c9e37` (quality), `408dea89af5f6789` (test coverage), `45df3b672a262c4c` (docs) — retrieve with `pickup(task_id, crew_id)` while the crew exists. Line numbers refer to `ee0b3b8` and may drift. Next step for whoever picks this up: work through **Assess first**, then write specs, design and tasks with `openspec instructions <artifact> --change <name>`.

## Why

Several settings are documented as tunable but `install.sh` never passes them, and the installer and transport disagree on some inputs. Operators set values that silently do nothing.

## Findings

| Severity | Finding | Where | Who | Status |
|---|---|---|---|---|
| Medium | Not passed into the container: `GA_PREWARM_*`, `GA_RATE_LIMIT_DASHBOARD_AUTH`, `GA_FILE_SECRET`; `KC_IMAGE` and `PODMAN_SOCKET` ignored in `ghostship.conf`. | `install.sh` compose env (`:739-785`) | D | Read only |
| Medium | `GA_ORDERS_DIR` and `GA_TLS_CERTFILE`/`KEYFILE` pass host paths that are never mounted, so the transport can't read them. | `install.sh:729-737`, `:771`, `:785` | D | Read only |
| Medium | `PORT` only sets Caddy's host port; the transport is hard-coded to 64057 inside the container. | `install.sh:742`, `:861` | D | Read only |
| Low | Negative `GA_MAX_ACTIVE_CREWS` silently disables the limit (undocumented); `GA_TASK_TIMESTAMP_TTL_SECS` has no floor despite the comment. | `config.py:43-51`; `lifecycle.py:282`, `:702` | Q | Read only |
| Low | Exported shell variables do reach the compose file for anything not literal-assigned in `install.sh`, contrary to the docs. | `install.sh:52-103`, `:716` | D | Read only |

## Assess first

- For each unpassed setting, decide: pass it through, mount it, or remove it from the docs as internal.
- Docs not yet verified against the code: `docs/forks.md`, `docs/agents.md`, most of `docs/portal.md`, the Admiral signing and secrets sections of `docs/auth.md`, and the fixed headless overrides table in `configuration.md`.

## What Changes

- Pass or retire each listed setting; mount `GA_ORDERS_DIR` and TLS certs when set.
- Reject negative `GA_MAX_ACTIVE_CREWS` (or document it as "disable"); floor `GA_TASK_TIMESTAMP_TTL_SECS` or fix the comment.
- Update `docs/configuration.md` and `config/ghostship.conf.example` as each setting is resolved, including the ambient-shell-variable note.

## Capabilities

### New Capabilities

- None expected.

### Modified Capabilities

- `installation`, `config-file`.

## Impact

`scripts/install.sh`, `transport/config.py`, `docs/configuration.md`, `config/ghostship.conf.example`.
