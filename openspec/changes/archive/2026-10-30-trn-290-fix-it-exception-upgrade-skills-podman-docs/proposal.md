# Proposal

## Why

Independent review of the v0.10.0 release (indy-review crew, 2026-10-30) identified
three small correctness and documentation issues worth fixing promptly.

## What Changes

### H-4 — Exception string disclosure in 500 responses

`transport/server.py` returns `str(exc)` directly in several error responses,
including a `JSONResponse({"error": str(exc)}, status_code=500)` on the internal
fleet endpoint. Raw Python exception messages (which may contain internal paths,
module names, or configuration details) are sent to callers. Replace with a
generic message and ensure the real exception is logged server-side.

Affected lines: `server.py:1097, 1104, 1470, 1516, 1581`.

### L-Q4 — `ghostship upgrade --skills` looks for the wrong script path

The `--skills` branch in the `ghostship` CLI (`ghostship` line ~108) constructs:
```python
script = _ghostship_dir() / "scripts" / "install.sh"
```
The actual script lives at `bin/install.sh`, not `scripts/install.sh`. The flag
silently returns "error: script not found" on every invocation. Fix: change the
path to `bin/install.sh`.

### H-7/M-D1 — PODMAN_SOCK vs PODMAN_SOCKET docs confusion

`docs/troubleshooting.md` tells users to `export PODMAN_SOCK=/actual/path/...`
for the install-time override. `docs/configuration.md` lists `PODMAN_SOCKET` as
the user-facing variable. These are two different things — `PODMAN_SOCK` is a
shell variable read by `install.sh` at install time; `PODMAN_SOCKET` is the
container env var the transport reads at runtime. The distinction is never
explained, which confuses operators overriding the socket path.

## Capabilities

### Modified Capabilities

- `transport/error-handling`: add requirement that error responses must not
  disclose raw exception messages.

## Impact

- `transport/server.py` — replace `str(exc)`/`str(e)` in error responses
- `ghostship` (CLI) — fix `scripts/install.sh` → `bin/install.sh`
- `docs/troubleshooting.md` and `docs/configuration.md` — add clarifying note
  distinguishing install-time `PODMAN_SOCK` from runtime `PODMAN_SOCKET`
