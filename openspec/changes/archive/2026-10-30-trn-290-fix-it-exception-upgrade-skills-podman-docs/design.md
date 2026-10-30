# TRN-290 Design

## Fix 1 — H-4: Exception disclosure in transport/server.py

### Affected lines

Five call sites in `transport/server.py` return raw exception strings to callers:

| Line | Handler | Exception class | HTTP status |
|-----:|---------|-----------------|-------------|
| 1097 | `_resolve_crew_for_proxy` | `KeyError, ValueError` | 404 |
| 1104 | `_resolve_crew_for_proxy` | `RuntimeError` | 502 |
| 1470 | `_handle_crew_dashboard_post` | `RuntimeError` | 409 |
| 1516 | `_handle_crew_dashboard_delete` | `KeyError, ValueError` | 404 |
| 1581 | `_handle_internal_crews_get` | `Exception` | 500 |

### Decision: generic message + server-side log

Replace each `str(e)` / `str(exc)` in the returned response body with a static
generic message. Log the real exception at the appropriate level first so
nothing is lost for debugging. Use the exception variable that is already in
scope — no re-binding needed.

**4xx paths (404, 409):** the status code itself is informative. Return a
short, stable client-facing message that describes *what* failed without
leaking internals:

- 404 from `_require_crew`: `"Crew not found"` (the crew_id is already in the
  URL; repeating it in the body adds nothing and leaking the internal
  registry/ValueError text adds risk)
- 502 from `_ensure_crew_running`: `"Failed to start crew"` (RuntimeError
  messages can include container names, socket paths, etc.)
- 409 from port allocation: `"No dashboard port available"` (RuntimeError from
  `_caddy_portal.allocate_port` may include port-range config values)

**5xx path (500):** already logs at `logger.error`. Keep the log call; change
the JSON body from `{"error": str(exc)}` to `{"error": "Internal server error"}`.

### 4xx vs 5xx distinction

The 4xx sites are client errors — the caller can act on the status code alone.
No internal detail belongs in the body. The 500 site is a server-side failure
in `_handle_internal_crews_get` — the existing `logger.error` call is
sufficient for operator diagnosis; the response body need only signal failure.
No special treatment needed for the 4xx vs 5xx split beyond the message choices
above.

### Log levels

| Line | Current log | Change |
|-----:|-------------|--------|
| 1097 | none | add `logger.warning("_resolve_crew_for_proxy require_crew: %s", e)` before return |
| 1104 | none | add `logger.warning("_resolve_crew_for_proxy ensure_running: %s", e)` before return |
| 1470 | none | add `logger.warning("_handle_crew_dashboard_post allocate_port: %s", e)` before return |
| 1516 | none | add `logger.warning("_handle_crew_dashboard_delete require_crew: %s", e)` before return |
| 1581 | `logger.error("_handle_internal_crews_get: %s", exc)` | keep as-is, only change response body |

---

## Fix 2 — L-Q4: upgrade --skills uses scripts/install.sh instead of bin/install.sh

### Confirmed wrong path

`repo/ghostship` around line 109 (the `--skills` subprocess branch in
`cmd_upgrade`):

```python
# Current (WRONG):
script = _ghostship_dir() / "scripts" / "install.sh"

# Fast path (correct reference):
_exec_script("bin/install.sh", install_args)
```

`scripts/` contains only `generate-openspec-skills.js`,
`generate_openapi.py`, `run.sh`, and `security_scan.py`. `scripts/install.sh`
does not exist. The fast path (`_exec_script("bin/install.sh", ...)`) and every
other call site (`cmd_install`, `cmd_uninstall`) correctly use `bin/`.

### Decision: one-line fix — change `"scripts"` to `"bin"`

```python
# After fix:
script = _ghostship_dir() / "bin" / "install.sh"
```

No other changes needed in this function. The `script.exists()` guard remains
correct — it will now find the real `bin/install.sh`.

---

## Fix 3 — H-7 / M-D1: PODMAN_SOCK vs PODMAN_SOCKET docs discrepancy

### Confirmed naming inconsistency

| File | Variable used | Context |
|------|--------------|---------|
| `docs/configuration.md` line 18 | `PODMAN_SOCKET` | env var table, canonical reference |
| `docs/configuration.md` line 232 | `PODMAN_SOCKET` | config section mapping |
| `docs/troubleshooting.md` line 70 | `PODMAN_SOCK` | "Podman Socket Not Found" workaround |
| `docs/manual-install.md` lines 88, 90 | `PODMAN_SOCK` | manual install notes |

`configuration.md` is the authoritative reference (`PODMAN_SOCKET` is the
correct env var name read by `install.sh`). The troubleshooting and manual
install docs use `PODMAN_SOCK`, which `install.sh` does not read — a user
following those instructions sets a variable that is silently ignored.

### Decision: add a clarifying note in troubleshooting.md and configuration.md

**In `docs/troubleshooting.md`**, in the "Podman Socket Not Found" section,
add an inline note immediately after the `export PODMAN_SOCK=…` code block:

> **Note:** The correct environment variable read by `install.sh` is
> `PODMAN_SOCKET` (with the `ET` suffix), not `PODMAN_SOCK`. Replace
> `PODMAN_SOCK` with `PODMAN_SOCKET` in the export above.

**In `docs/configuration.md`**, in the `PODMAN_SOCKET` env var row description,
add a parenthetical after the existing text:

> (Note: some older docs and error messages may refer to this as `PODMAN_SOCK`;
> the variable `install.sh` reads is `PODMAN_SOCKET`.)

Do not change `docs/manual-install.md` in this change — it is a larger file
and the `PODMAN_SOCK` references there are embedded in prose that would need
wider editorial review. File a follow-up if needed.

### Scope decision: docs-only

The correct variable name (`PODMAN_SOCKET`) is already read by `install.sh`.
No code change is required. The fix is documentation clarity to prevent silent
misconfiguration.
