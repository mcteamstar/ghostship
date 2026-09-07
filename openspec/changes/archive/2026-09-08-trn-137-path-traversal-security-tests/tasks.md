## 1. Path traversal fix

- [x] 1.1 In `transport/files.py`, change `_safe_workspace_path()` prefix check from `str(resolved).startswith(str(root))` to `str(resolved).startswith(str(root) + "/")`
- [x] 1.2 Handle the root path edge case: when `resolved == root` exactly (e.g. path is `""` or `"."`), the check should pass — add `or resolved == root` to the condition

## 2. Dead code removal

- [x] 2.1 In `transport/server.py`, remove the dead colon check from `_validate_next_url()`: delete the `if ":" in url.split("/")[0]: return "/"` branch (the leading-slash guard above already covers this)

## 3. Unit tests — _safe_workspace_path

- [x] 3.1 Add tests in `tests/unit/test_files.py` (or new `test_path_security.py`) covering:
  - Path traversal via `../` — expect `ValueError`
  - Adjacent directory (e.g. root=`/workspace`, path resolves to `/workspace-evil/secret`) — expect `ValueError`
  - Symlink that resolves outside root — expect `ValueError`
  - Valid path inside workspace — expect success
  - Path equal to root exactly — expect success

## 4. Unit tests — _validate_next_url

- [x] 4.1 Add tests in `tests/unit/test_server.py` covering:
  - `//evil.com` — expect `"/"`
  - `javascript:alert(1)` — expect `"/"`
  - Empty string `""` — expect `"/"`
  - Valid path `/dashboard/` — expect `"/dashboard/"`
  - Path with query string `/foo?bar=1` — verify it passes or falls back appropriately

## 5. Unit tests — _parse_bearer_token

- [x] 5.1 Add tests in `tests/unit/test_auth.py` covering:
  - Valid `Bearer abc123` — expect `"abc123"`
  - Empty string — expect `None`
  - `"Bearer "` with no token — expect `None`
  - `"Bearer tok en"` with embedded space in token — verify behaviour
  - Non-Bearer scheme `"Basic abc"` — expect `None`
  - Exactly 7 chars `"Bearer"` (no space) — expect `None`

## 6. Unit tests — _validate_ref

- [x] 6.1 Add tests covering:
  - Ref starting with `-` (e.g. `--output=/tmp/pwned`) — expect rejection
  - Ref with shell metacharacters (e.g. `main; rm -rf /`) — expect rejection
  - Empty string — expect rejection
  - Valid ref `main` — expect pass
  - Valid ref `release/0.3.1` — expect pass
  - Valid commit hash (40 hex chars) — expect pass

## 7. Validation

- [x] 7.1 Run `openspec validate trn-137-path-traversal-security-tests`
- [x] 7.2 Run `bash tests/run.sh --unit` — all tests pass
