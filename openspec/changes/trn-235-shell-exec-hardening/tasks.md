# Tasks

## 1. SEC-1 — Replace sh -c chunk-append in _inject_claude_auth and _inject_codex_auth

- [x] 1.1 In `transport/lifecycle.py`, rewrite `_inject_claude_auth` to pass the credential tar bytes directly to `podman.container_archive_put` instead of the base64-encode → chunk → sh-c-printf → base64-d pipeline. Remove the `CHUNK` constant, the chunking loop, the tmp file path, and all `sh -c` exec calls. Verify: `grep -n "sh.*-c\|printf.*chunk" transport/lifecycle.py` returns no hits in `_inject_claude_auth`. Add a unit test asserting `container_exec` is never called with `sh` or `printf` for this path.
- [x] 1.2 Apply the same replacement to `_inject_codex_auth` (`~L3458–3461`). Verify: same grep check; same unit test pattern. Run `tests/run.sh --unit` and confirm existing Claude/Codex auth tests still pass.

## 2. SEC-2 — Replace python3 -c in _write_dashboard_cookie

- [x] 2.1 In `transport/lifecycle.py`, rewrite `_write_dashboard_cookie` to build a minimal in-memory tar containing the cookie string (mode 0600) and call `container_archive_put`. Remove the `python3 -c` f-string exec entirely. Verify: `grep -n "python3.*-c\|repr.*cookie" transport/lifecycle.py` returns no hits in this function. Add a unit test asserting `container_exec` is never called with `python3` for this path, and the cookie value is correctly written via archive.

## 3. SEC-3 — Config.__repr__ masking

- [x] 3.1 In `transport/config.py`, add a `__repr__` method to the `Config` dataclass that replaces non-empty values of `kiro_api_key`, `anthropic_api_key`, `openai_api_key`, and `claude_code_oauth_token` with `"***"`. Verify: unit test confirms `repr(Config(kiro_api_key="secret", ...))` does not contain `"secret"` and does contain `"***"`. Run `tests/run.sh --unit` and confirm pass.

## 4. Integration check

- [x] 4.1 Run `tests/run.sh --unit` to confirm all three fixes pass together with no regressions in existing auth injection tests.

## Workflow follow-up

- Archive the change after review.
