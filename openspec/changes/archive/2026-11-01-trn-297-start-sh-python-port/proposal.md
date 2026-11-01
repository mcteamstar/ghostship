# TRN-297 — Port start.sh to Python (start_main.py)

## Problem

`bin/start.sh` is 170 lines of bash. It was partially modularised in TRN-294:
`start_ops.py` handles config resolution (no eval), but all the real work
remains in bash:

- Podman machine/socket start (macOS + Linux paths)
- `podman compose up -d` via subprocess
- Health check polling via `curl`
- `eval "${_COMPOSE_ENV} podman compose ..."` — the last eval pattern in the
  start path

TRN-294 turned `install.sh` into a ~80-line prereq-check + `exec python3
install_main.py`. The same pattern should apply to `start.sh`.

## Proposed fix

Create `bin/lib/start_main.py` that reuses existing modules:

- `podman_setup.py` — already handles machine start/socket resolution
- `compose.py` / `start_ops.py` — config resolution, DATA_DIR, compose path
- `portal_host.py` — health check URL construction
- `subprocess` — `podman compose up -d`, health check (replacing curl)

Reduce `bin/start.sh` to ~30 lines: prereq check (python3, podman,
podman-compose) + `exec python3 bin/lib/start_main.py "$@"`.

Eliminates the last `eval "${_COMPOSE_ENV} podman compose ..."` in the start
path.

## Out of scope

- `bin/uninstall.sh` — complex platform teardown, acceptable as bash
- Any changes to `bin/install.sh` or `install_main.py`
