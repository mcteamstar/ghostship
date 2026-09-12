## Why

Four related hygiene issues in `podman.py`, found by the 0.4.0 independent review:

1. **Bare `except Exception: pass`** in `container_stop`, `container_remove`, `volume_create`, `volume_remove`, `secret_remove`, `network_disconnect`, `network_rm`, and worker cleanup — masks real infra failures as confusing downstream errors.
2. **httpx2 clients never closed** — module-level `httpx2.Client` / `httpx2.AsyncClient` created at import, no atexit/shutdown hook, hard to mock cleanly.
3. **`container_exec` leaks response object** — accesses `.content` without closing; asymmetric with `*_checked` siblings.
4. **`container_exec_pty_stdin` / `container_exec_stdin` leak raw socket on header-phase raise** — no try/finally around connect + read-headers.

Note: the codebase migrated from `httpx` to `httpx2` in 0.4.0 — all fixes target `httpx2` client types.

## What Changes

- Narrow `except Exception: pass` to expected HTTP statuses (409/404); log WARNING for unexpected errors.
- Add `atexit` close for the module-level httpx2 clients.
- Wrap `container_exec` response in a context manager.
- Add try/finally to raw-socket connect + header-read phases.

## Capabilities

### Modified Capabilities

- `crew-orchestration`: `podman.py` resource cleanup behaviour changes — errors that were silently swallowed now propagate or log.

## Impact

- `transport/podman.py` — all four fixes
- `tests/unit/test_podman.py` (or existing test files) — verify narrowed exception handling
