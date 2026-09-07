## Why

Independent review (2026-09-07) identified a path traversal vulnerability in `_safe_workspace_path()` and zero test coverage on four security-critical functions — any of which accepting unexpected input could silently allow path escapes, authentication bypass, or open redirects. These are pre-release blockers.

## What Changes

- `transport/files.py` — fix `_safe_workspace_path()` prefix check: append `/` to root before `startswith` to prevent adjacent-directory bypass
- `transport/server.py` — remove dead colon check in `_validate_next_url()` (the check never fires; the leading-slash guard already handles the attack vector)
- `tests/unit/test_files.py` (new or extended) — add unit tests for `_safe_workspace_path()` covering path traversal, adjacent directory, symlink escape, valid paths
- `tests/unit/test_server.py` (or new file) — add unit tests for `_validate_next_url()` covering `//evil.com`, `javascript:alert()`, empty string, bare colon path, valid path
- `tests/unit/test_auth.py` (new or extended) — add unit tests for `_parse_bearer_token()` covering empty token, embedded space, exactly-7-char input, unicode in scheme, valid token
- `tests/unit/test_files.py` or `test_server.py` — add unit tests for `_validate_ref()` covering leading dash, shell metacharacters, empty string, valid ref

## Capabilities

### New Capabilities
- none

### Modified Capabilities
- `file-transfer-security`: `_safe_workspace_path()` path traversal fix — the existing requirement changes in observable boundary behaviour
- `installation/client-only`: no changes

### Modified Capabilities
- `file-transfer-security`: behavioural fix to `_safe_workspace_path()` prefix check

## Impact

- `transport/files.py` — one-line fix to `_safe_workspace_path()`
- `transport/server.py` — remove dead colon check from `_validate_next_url()`
- `transport/auth.py` — no code changes; tests only
- `tests/unit/` — new tests for four functions
