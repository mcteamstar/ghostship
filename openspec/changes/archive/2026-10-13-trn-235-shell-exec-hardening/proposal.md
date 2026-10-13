# Proposal

**Plane ticket:** TRN-235

## Why

Two credential injection paths in `transport/lifecycle.py` use shell exec (`sh -c` and `python3 -c`) to write files into crew containers. Both are safe today because the data they write is base64 or URL-safe base64 — alphabets with no shell metacharacters. The safety relies on knowing what the data is, not on a structural guarantee. A future change that writes non-base64 content through either path would open a shell injection surface without any obvious warning. Additionally, the `Config` dataclass holds live credential values with no `__repr__` masking, so any log call that includes `str(cfg)` or `repr(cfg)` emits live credentials unredacted.

## What Changes

- **SEC-1 — Replace `sh -c` chunk-append with `container_archive_put`**: `_inject_claude_auth` and `_inject_codex_auth` both append base64 chunks to a tmp file via `podman.container_exec(container, ["sh", "-c", f"printf '%s' '{chunk}' >> {tmp}"])`. Replace with a single `container_archive_put` call that writes the decoded credential as a tar member directly into the target path. Eliminates the tmp file, the chunking loop, and the shell exec entirely.
- **SEC-2 — Replace `python3 -c` cookie write with `container_archive_put`**: `_write_dashboard_cookie` interpolates the cookie value via `repr()` into an inline `python3 -c` subprocess. Replace with `container_archive_put` writing the cookie string as a tar member with mode 0600.
- **SEC-3 — Add `__repr__` masking to `Config`**: Add a `__repr__` override to the `Config` dataclass that replaces sensitive field values with `***`. Fields: `kiro_api_key`, `anthropic_api_key`, `openai_api_key`, `claude_code_oauth_token`. Alternatively, call `register_secret()` for each in `from_env()`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `secret-delivery-hardening`: add requirements that credential injection uses `container_archive_put` (not shell exec), and that `Config` repr masks sensitive fields.

## Impact

- `transport/lifecycle.py` — `_inject_claude_auth`, `_inject_codex_auth`, `_write_dashboard_cookie`
- `transport/config.py` — `Config.__repr__`
- Tests: unit tests verifying no `sh -c` in injection paths; repr masking test
