# TRN-93 Tasks — Security Hardening

## 1. stdin delivery for inject_admiral_secret.py

- [x] 1.1 Add `container_exec_stdin` to the abstract `PodmanClient` base class in `transport/podman.py`. Signature: `container_exec_stdin(self, container: str, cmd: list[str], stdin_data: bytes) -> str`. This method runs a one-shot exec, writes `stdin_data` to the process's stdin, waits for exit, and returns stdout as a string.
- [x] 1.2 Implement `container_exec_stdin` in `PodmanSocketClient` using the Podman exec API (`POST /libpod/containers/{name}/exec` + `POST /libpod/exec/{id}/start`). Attach stdin via the hijacked connection and write `stdin_data` before closing the write side. Demux the response using the existing `_demux` helper.
- [x] 1.3 Add a `container_exec_stdin` stub to the `MockPodmanClient` (and any other mock/test doubles in `tests/`) that records the call and returns a configurable response.
- [x] 1.4 Update `transport/container_scripts/inject_admiral_secret.py`: remove the `argv[2]` argument; read the secret from `sys.stdin.read().strip()` instead. Update the usage docstring and `main()` signature check (now expects exactly 2 args: script name + dest path).
- [x] 1.5 Update the call site in `transport/lifecycle.py` (`_finish_crew_setup`): replace the `container_exec_checked(...)` call for `inject_admiral_secret.py` with `container_exec_stdin(container, ["python3", f"{SCRIPTS_DIR}/inject_admiral_secret.py", f"{KIRO_CREW_DIR}/.admiral_secret"], admiral_secret.encode())`.
- [x] 1.6 Verify existing unit tests for `inject_admiral_secret.py` still pass; update any test that passes the secret as `argv[2]` to pass it via `stdin` instead.

## 2. At-rest credential hygiene in crews.json

- [x] 2.1 Add `_secret_identifier(value: str) -> str` helper to `transport/lifecycle.py`. Returns `"sha256:" + hashlib.sha256(value.encode()).hexdigest()[:16]` — a non-reversible opaque label.
- [x] 2.2 In `_finish_crew_setup`, after `admiral_secret` and `policy_signing_key` have been injected into the container, replace their values in `crew_entry` before writing to `crews.json`. Use distinct field names: `"admiral_secret_id": _secret_identifier(admiral_secret)` and `"policy_signing_key_id": _secret_identifier(policy_signing_key)`. Remove (or do not add) the `"admiral_secret"` and `"policy_signing_key"` plaintext fields from `crew_entry`.
- [x] 2.3 Audit all read-back paths: `grep -rn 'admiral_secret\|policy_signing_key'` in `transport/` and confirm no code path re-reads these fields from `crews.json` for operational use (as opposed to logging). Document any find in a comment; the only expected reads are in tests and in `docs/auth.md`.
- [x] 2.4 Update `docs/auth.md` — in the "Storage" section, replace the sentence "Both `admiral_secret` and `policy_signing_key` are stored in plaintext in `crews.json`" with an accurate description of the identifier scheme and remove the TRN-16 forward reference.

## 3. Container hardening flags

- [x] 3.1 In `transport/podman.py`, update `container_create` to add `"no_new_privileges": True` and `"cap_drop": ["CAP_NET_RAW", "CAP_SYS_ADMIN"]` to the container spec dict before the `_req` call.
- [x] 3.2 In `transport/podman.py`, update the `worker_run` spec dict to include `"no_new_privileges": True` and `"cap_drop": ["CAP_NET_RAW", "CAP_SYS_ADMIN"]`.
- [x] 3.3 Confirm existing unit tests for `container_create` and `worker_run` (in `tests/unit/test_podman.py`) still pass. Add assertions that the new fields are present in the spec dict passed to the Podman API mock.

## 4. KC_GATEWAY_TOKEN_TTL validation

- [x] 4.1 Add `_validate_token_ttl(value: str, default: str = "24h") -> str` to `transport/config.py`. The function accepts values matching `^\d+[smhd]$` with the numeric part > 0. On mismatch, logs `logging.warning("KC_GATEWAY_TOKEN_TTL=%r is invalid; falling back to %r", value, default)` and returns `default`. Import `logging` and `re` at the top of `config.py` if not already present.
- [x] 4.2 In `Config.from_env()`, wrap the `kc_gateway_token_ttl` assignment: `kc_gateway_token_ttl=_validate_token_ttl(os.environ.get("KC_GATEWAY_TOKEN_TTL", "24h"))`.
- [x] 4.3 Add unit tests for `_validate_token_ttl` in `tests/unit/` (inline in the new TRN-93 test file): valid values `"24h"`, `"3600s"`, `"7d"`, `"30m"` are returned unchanged; invalid values `"banana"`, `"0h"`, `"-1m"`, `""`, `"24"` trigger a WARNING and return `"24h"`.

## 5. Audit logging for file-transfer events

- [x] 5.1 In `transport/server.py`, find the `evac()` MCP tool function. After a presigned download URL is successfully generated, add a call to `_security.audit_auth_event(action="presign_evac", outcome="issued", source=None)`. Import `_security` is already present.
- [x] 5.2 In `transport/server.py`, find the `supply()` MCP tool function. After a presigned upload URL is successfully generated, add a call to `_security.audit_auth_event(action="presign_supply", outcome="issued", source=None)`.
- [x] 5.3 In `transport/server.py`, find `_verify_file_token`. Add audit calls for each exit path: `outcome="expired"` for an expired token, `outcome="invalid"` for a bad HMAC or truncated signature, `outcome="valid"` for a verified token. Pass `action="verify_file_token"`. Do not log the token value or HMAC.
- [x] 5.4 Verify that none of the new audit events include the presigned URL, the HMAC secret, or the raw API key. The `redact()` helper in `security.py` is the backstop; confirm registered secrets are in scope.

## 6. Tests

- [x] 6.1 Create `tests/unit/test_trn93_security_hardening.py`. Add test class `TestStdinSecretDelivery` with a test confirming `inject_admiral_secret.py`'s `inject_admiral_secret(dest, stdin_secret)` API writes the correct value to the destination file and does NOT accept an `argv[2]` argument.
- [x] 6.2 Add `TestCrewsJsonHygiene` — mock `_finish_crew_setup` to intercept the `crews.json` write; assert that `admiral_secret` and `policy_signing_key` are absent from the written entry dict, and that `admiral_secret_id` and `policy_signing_key_id` are present as `sha256:<hex>` strings.
- [x] 6.3 Add `TestContainerHardeningFlags` — assert that `container_create` spec includes `no_new_privileges: True` and both capability names in `cap_drop`, and that `worker_run` spec includes the same.
- [x] 6.4 Add `TestTokenTTLValidation` in the same file (or in `test_trn93_...`): exercises all branches of `_validate_token_ttl`. Uses `assertLogs` or mock logger to confirm WARNING is emitted on invalid input.
- [x] 6.5 Add `TestFileTransferAudit` — use a mock `audit_auth_event` to verify it is called with the correct `action`/`outcome` for each of: successful evac presign, successful supply presign, valid token verification, invalid token, expired token.
- [x] 6.6 Run `python3 -m pytest tests/unit/test_trn93_security_hardening.py -q` (or equivalent) — all tests pass.
- [x] 6.7 Run the full unit test suite `python3 -m pytest tests/unit/ -q` — no regressions.

## 7. Documentation

- [x] 7.1 Update `docs/auth.md` per task 2.4 (crews.json storage section).
- [x] 7.2 Add a note to `docs/security.md` (under "Secrets management") that `admiral_secret` is delivered to container scripts via stdin, not process arguments, and that `crews.json` retains only a non-reversible identifier after injection.
- [x] 7.3 Add commented-out `KC_GATEWAY_TOKEN_TTL` entry to `config/ghostship.conf.example` with the default value and a brief inline comment describing the accepted format (`<N>[s|m|h|d]`, e.g. `24h`).
