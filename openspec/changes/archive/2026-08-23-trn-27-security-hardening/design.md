## Context

See proposal.md — Why. Two security issues: GA_API_KEY leaking through `podman inspect`/`/proc` due to `-e` env-var injection, and a write-side TOCTOU in `_handle_login_post` (sentinel set after lock release) plus an unguarded clear in `_handle_login_get`.

Current state:
- `install.sh` line 304: `-e "GA_API_KEY=${GA_API_KEY:-}"` passes the key as an environment variable.
- `transport/server.py` line 134: `GA_API_KEY = os.environ.get("GA_API_KEY", "").strip()`.
- `_handle_login_post` (line 1869): acquires `_login_pending_lock`, checks both guards, releases lock (~line 1896), then ~130 lines later (line 2025) re-acquires lock to set `_login_pending`.
- `_handle_login_get` (line 2084): unconditionally clears `_login_pending = None` without checking which container it belongs to.

## Goals / Non-Goals

**Goals:**
- Eliminate API key exposure via container environment/process metadata.
- Close the write-side TOCTOU: make it impossible for two concurrent `POST /login` to both pass guards and start containers.
- Guard the `_login_pending = None` clear so a newly-started concurrent login is not clobbered.
- Maintain backward compatibility: existing installations that only have the env-var form continue to work (deprecated fallback).

**Non-Goals:**
- Rotating or expiring the API key (out of scope — no key rotation mechanism today).
- Encrypting ga-kiro-auth at rest (separate concern, not a regression).
- Converting other env vars to secrets (only GA_API_KEY has a security sensitivity here).

## Decisions

### D1: Podman secret for GA_API_KEY

**Choice:** Use `podman secret create ga-api-key` + `--secret ga-api-key` on the container, read from `/run/secrets/ga-api-key` inside.

**Rationale:** Podman secrets are the idiomatic way to pass sensitive data to containers. The secret is stored in Podman's secret store (by default `~/.local/share/containers/storage/secrets/`), never appears in `podman inspect`, and is bind-mounted read-only into the container at `/run/secrets/<name>`. No changes to the container image are needed — the file is injected at runtime.

**Alternative considered:** Volume-mount a key file from `DATA_DIR`. Rejected because it requires the operator to manage file permissions manually and doesn't integrate with Podman's lifecycle (e.g. `podman secret ls`, `podman secret rm` for cleanup).

### D2: Deprecated env-var fallback in the transport

**Choice:** If `/run/secrets/ga-api-key` is absent, fall back to `os.environ.get("GA_API_KEY")` and emit a deprecation warning at startup.

**Rationale:** Existing deployments upgraded in-place (just pulling a new image) won't have the secret created yet. The fallback gives them time to re-run `install.sh`. The warning makes it visible.

### D3: Early sentinel in _handle_login_post

**Choice:** Set `_login_pending` to a lightweight sentinel dict `{"container": None, "started_at": time.time(), "state": "starting"}` immediately inside the same lock acquisition that performs the guard checks. After the container starts successfully, update it in-place (under lock) with the real container name. On failure, clear it.

**Rationale:** Moving the sentinel write into the same critical section as the guards closes the TOCTOU: the lock is held from guard-check through sentinel-write, so a concurrent request necessarily sees a non-None sentinel and returns 409. The sentinel must carry enough state to distinguish "starting" from "started" so `GET /login` can return a helpful status.

**Alternative considered:** Extending the lock to cover the entire container-start sequence (~1–5s). Rejected — holding a global lock that long blocks all other login-related requests and any code that acquires the same lock.

### D4: Container-name-guarded clear in _handle_login_get

**Choice:** Before clearing `_login_pending = None`, compare `pending["container"]` with the container that was just completed. Only clear if they match.

**Rationale:** If a new login started between nuke and clear (window is ~ms but possible under load), clearing unconditionally would wipe the new login's sentinel. The name comparison is cheap and fully deterministic (container names include a random token).

## Risks / Trade-offs

- **[Risk] Secret recreation on re-install** — `podman secret create` fails if the name already exists. → Mitigation: `podman secret rm ga-api-key 2>/dev/null || true` before create.
- **[Risk] Rootless Podman secret store permissions** — On some distros the secret store dir has open permissions by default. → Mitigation: Document that the operator should ensure `~/.local/share/containers/` is mode 700 (install.sh already runs as the user, not root).
- **[Risk] Early sentinel leaks on container-start failure** — If `_start_login_container` raises, the sentinel is set but no container exists. → Mitigation: Wrap in try/except; on failure, re-acquire lock and clear sentinel before returning 500.
- **[Trade-off] Deprecated fallback adds complexity** — Two read paths for the API key. Acceptable because: (a) it's ~5 lines of code, (b) the fallback is delete-safe in a future release once the old path is sunset.

## Migration Plan

1. `install.sh` changes are applied on next `install.sh` invocation (operator pulls and re-runs).
2. Existing containers continue to work via the env-var deprecation fallback until the operator re-runs `install.sh`.
3. No data migration needed — the API key file in DATA_DIR is unchanged; it's just the delivery mechanism to the container that changes.
4. Rollback: revert to previous `install.sh` and image; the env-var path still works.
