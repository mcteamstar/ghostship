# TRN-290 Tasks

## T1 — Fix upgrade --skills path in repo/ghostship

- [ ] In `repo/ghostship` around line 109, change:
  ```python
  script = _ghostship_dir() / "scripts" / "install.sh"
  ```
  to:
  ```python
  script = _ghostship_dir() / "bin" / "install.sh"
  ```

## T2 — Replace str(exc)/str(e) in transport/server.py error responses

- [ ] **Line 1097** (`_resolve_crew_for_proxy`, 404 path):
  - Add `logger.warning("_resolve_crew_for_proxy require_crew: %s", e)` before the return
  - Change `PlainTextResponse(str(e), status_code=404)` → `PlainTextResponse("Crew not found", status_code=404)`

- [ ] **Line 1104** (`_resolve_crew_for_proxy`, 502 path):
  - Add `logger.warning("_resolve_crew_for_proxy ensure_running: %s", e)` before the return
  - Change `PlainTextResponse(str(e), status_code=502)` → `PlainTextResponse("Failed to start crew", status_code=502)`

- [ ] **Line 1470** (`_handle_crew_dashboard_post`, 409 path):
  - Add `logger.warning("_handle_crew_dashboard_post allocate_port: %s", e)` before the return
  - Change `JSONResponse({"error": str(e)}, status_code=409)` → `JSONResponse({"error": "No dashboard port available"}, status_code=409)`

- [ ] **Line 1516** (`_handle_crew_dashboard_delete`, 404 path):
  - Add `logger.warning("_handle_crew_dashboard_delete require_crew: %s", e)` before the return
  - Change `PlainTextResponse(str(e), status_code=404)` → `PlainTextResponse("Crew not found", status_code=404)`

- [ ] **Line 1581** (`_handle_internal_crews_get`, 500 path):
  - Keep the existing `logger.error("_handle_internal_crews_get: %s", exc)` log call unchanged
  - Change `JSONResponse({"error": str(exc)}, status_code=500)` → `JSONResponse({"error": "Internal server error"}, status_code=500)`

## T3 — Add clarifying note to docs about PODMAN_SOCK vs PODMAN_SOCKET

- [ ] In `docs/troubleshooting.md`, "Podman Socket Not Found" section, immediately after the
  `export PODMAN_SOCK=/actual/path/podman.sock` code block, add:

  ```
  > **Note:** The correct environment variable read by `install.sh` is
  > `PODMAN_SOCKET` (with the `ET` suffix), not `PODMAN_SOCK`. Replace
  > `PODMAN_SOCK` with `PODMAN_SOCKET` in the export above.
  ```

- [ ] In `docs/configuration.md`, in the `PODMAN_SOCKET` row of the environment variable table,
  append to the existing description:
  ```
  (Note: some older docs and error messages may refer to this as `PODMAN_SOCK`; the variable `install.sh` reads is `PODMAN_SOCKET`.)
  ```

## T4 — Run tests and verify

- [ ] Run the transport unit test suite: `python -m pytest tests/unit/ -x -q`
- [ ] Confirm no test references `str(e)` or `str(exc)` in server response assertions that
  would break with the new generic messages (search: `grep -r "str(e\b\|str(exc" tests/`)
- [ ] Confirm `ghostship upgrade --skills` succeeds end-to-end (or at minimum that
  `bin/install.sh` is found): `python -c "from pathlib import Path; p = Path('.') / 'bin' / 'install.sh'; print(p, p.exists())"`
