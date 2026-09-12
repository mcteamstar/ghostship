## Context

`podman.py` wraps the Podman HTTP API using module-level `httpx2` clients (post-0.4.0 migration from `httpx`). Four categories of issues:

1. **Bare `except Exception: pass`** in cleanup methods — hides socket/permission failures.
2. **Module-level httpx2 clients** with no shutdown hook — leaks connections, hard to mock.
3. **`container_exec` response leak** — `.content` read without closing.
4. **Raw socket leaks** in `container_exec_pty_stdin` / `container_exec_stdin` — no try/finally around connect+header phase.

## Goals / Non-Goals

**Goals:**
- Narrow exception handling to expected HTTP statuses; log WARNING for unexpected
- Add `atexit` close for the two module-level httpx2 clients
- Close `container_exec` response via context manager
- Add try/finally to raw-socket connect + header-read phase

**Non-Goals:**
- Restructuring PodmanClient as an async context manager (larger change, future ticket)
- Changing the module-level singleton pattern itself

## Decisions

**D1 — Narrow to `httpx2.HTTPStatusError` with status-code check**

Catch `httpx2.HTTPStatusError` and check `e.response.status_code in (404, 409)` (or whichever are expected per method). Any other exception (connection error, timeout, unexpected status) is logged at WARNING and re-raised. This is the pattern already used in `container_exec_checked`.

**D2 — `atexit.register` for client close**

After the two module-level clients are created, register `atexit.register(client.close)` and `atexit.register(async_client.aclose)` wrapped in a sync helper. Simple, zero-dependency, matches the stdlib-first style of the codebase.

**D3 — `container_exec` uses `with response:` context manager**

`httpx2.Response` supports the context manager protocol. Replace the bare `.content` access with `with client.send(req) as response: return response.content`.

**D4 — try/finally around socket connect + header read**

Both `container_exec_pty_stdin` and `container_exec_stdin` have a raw socket open + HTTP upgrade sequence. Wrap the entire upgrade block in `try/finally: sock.close()` where the `finally` only fires on failure (the success path transfers ownership).

## Risks / Trade-offs

- Narrowing the excepts may surface previously hidden errors in tests. Expected: existing tests should still pass; any new failures represent real bugs being unmasked.
