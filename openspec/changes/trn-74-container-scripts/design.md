## Context

14 `python3 -c "..."` call sites in `server.py`. The scripts cover: captain mail append, mail count read, mail subject read (with b64 workaround), auth injection, steering copy, model patching, auth extraction, auth wipe, crew config patching, policy injection, admiral secret injection, gateway readiness check, file transfer cleanup, and file transfer execution. See proposal.md for motivation.

Relevant existing constants:
- `_RAW_TRANSFER_SCRIPT`, `_ARCHIVE_TRANSFER_SCRIPT`, `_CLEANUP_TRANSFER_SCRIPT` (lines 5159–5210) — already named, easiest to extract
- `_read_subjects_src` (line 1662) — inline function that gets b64-encoded and exec'd; the worst offender
- `_ALL_MAILBOXES_SCRIPT` referenced at line 1640 — inline string assembly

## Goals / Non-Goals

**Goals:** Move all inline scripts to files. Make them importable and testable. Eliminate the b64-exec pattern. No behaviour changes.

**Non-Goals:** Change what the scripts do. Refactor `server.py` structure (that's TRN-71). Change the Containerfile base image or build process beyond adding the COPY directive.

## Decisions

### Script naming convention

Each script file is named after its primary operation in snake_case:

| Script file | Replaces | Function |
|---|---|---|
| `inject_auth.py` | line 2332 | `_inject_auth` |
| `read_auth.py` | line 2673 | `_read_auth_from_crew` |
| `wipe_auth.py` | line 3036 | `_handle_logout_post` |
| `append_captain_mail.py` | line 1576 | `_append_captain_mail` |
| `read_mail_counts.py` | line 1640 | `_read_all_mail_counts` |
| `read_mail_subjects.py` | line 1700 | `_read_all_mail_subjects` (replaces b64 hack) |
| `patch_models.py` | line 2629 | `_patch_models` |
| `patch_crew_config.py` | line 3318 | `_patch_crew_config` |
| `inject_policy.py` | line 3395 | `_inject_policy` |
| `inject_admiral_secret.py` | line 3436 | `_finish_crew_setup` |
| `check_gateway_ready.py` | line 3472 | `_finish_crew_setup` |
| `copy_steering.py` | line 2572 | `_copy_steering` |
| `transfer_raw.py` | line 5239 | `_cleanup_transfer_stage` / `_transfer_upload` (from `_RAW_TRANSFER_SCRIPT`) |
| `transfer_cleanup.py` | line 5239 | `_cleanup_transfer_stage` (from `_CLEANUP_TRANSFER_SCRIPT`) |

### Parameter passing

Scripts accept parameters via `sys.argv` positional args for simple cases (a path, a value) and via stdin JSON for complex structured inputs. No dynamic string construction in `server.py` — call sites become:

```python
podman.container_exec_checked(container, ["python3", "/scripts/inject_auth.py", KIRO_CLI_DB, b64_rows])
```

### Container path

Scripts are copied to `/scripts/` in the container image. `transport/Containerfile` currently copies individual files — switch the scripts directory to a single `COPY container_scripts/ /scripts/` directive.

### Testability

Script files live in `transport/container_scripts/`. Tests in `tests/unit/` can `import` them directly (adding `transport/` to `sys.path`) and test the logic with mock SQLite DBs, mock Maildir trees, etc. — no container or `container_exec` mock needed.

### b64-exec elimination

`_read_subjects_src` (line 1662) base64-encodes a multi-line Python function and passes it as a `-c` argument to avoid shell quoting. With file-based invocation this entire pattern is replaced by:

```python
podman.container_exec_checked(container, ["python3", "/scripts/read_mail_subjects.py", mailboxes_json])
```

## Risks / Trade-offs

- Scripts at `/scripts/` are a new convention — must be documented in `docs/architecture.md` or a comment in the Containerfile
- If TRN-71 reorganises the Containerfile further, this `COPY` directive will need to move with it. Acceptable — TRN-74 ships first and TRN-71 is aware of it
- 14 scripts × test coverage = significant test writing effort, but each test is simple (no mocking required)

## Migration Plan

Pure refactor inside the container image. Deploy via `install.sh` rebuilds the transport image with the new scripts baked in. No data migration. Scripts at `/scripts/` are only called by the transport — no external callers.
