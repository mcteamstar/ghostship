## 1. server.py — unify into single app

- [x] 1.1 Move file route handlers (`_handle_file_get`, `_handle_file_put`) from the file app's route list to the main app's route list
- [x] 1.2 Delete the second Starlette app (`file_app`) and its `uvicorn.serve()` call
- [x] 1.3 Remove `FILE_PORT` / `GA_FILE_PORT` constants and any references
- [x] 1.4 Add `GA_PUBLIC_URL` env var reading: prefer `GA_PUBLIC_URL`, fall back to `GA_MCP_PUBLIC_URL` with deprecation warning, default to `http://localhost:{PORT}`
- [x] 1.5 Update presigned URL generation in `supply()` and `evac()` to use `GA_PUBLIC_URL`

## 2. install.sh

- [x] 2.1 Remove `FILE_PORT=$((MCP_PORT + 1))` line
- [x] 2.2 Remove `-p ${FILE_PORT}:${FILE_PORT}` from the `podman run` invocation
- [x] 2.3 Confirm Caddyfile template is already a catch-all (no `/files*` separate upstream needed)

## 3. docs/configuration.md

- [x] 3.1 Add `GA_PUBLIC_URL` entry (replaces both split URL vars)
- [x] 3.2 Mark `GA_MCP_PUBLIC_URL` and `GA_FILE_PUBLIC_URL` as deprecated with migration note

## 4. Tests

- [x] 4.1 Update any test assertions that reference port 8001 or `GA_FILE_PUBLIC_URL`
- [x] 4.2 Add test: `evac()` presigned URL uses `GA_PUBLIC_URL` base
- [x] 4.3 Add test: fallback to `GA_MCP_PUBLIC_URL` when `GA_PUBLIC_URL` unset emits deprecation warning

## 5. Validation

- [x] 5.1 Run targeted tests: `python -m unittest transport.test_transport.FileTransferTests -v` (or equivalent)
- [x] 5.2 Run `openspec validate --specs`
