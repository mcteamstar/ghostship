## Why

`inject_auth.py` receives the kiro-cli SQLite auth payload as a base64 command-line
argument, which means the full credential string is visible in `/proc/<pid>/cmdline`
for the lifetime of the exec. `inject_policy.py` closed the identical gap for the
policy signing key (TRN-260 H-1) by switching to stdin delivery via
`container_exec_stdin`. The same hardening must be applied to `inject_auth.py` to
bring kiro auth injection in line with the project's `secret-delivery-hardening` spec.

## What Changes

- `transport/container_scripts/inject_auth.py` — read the `b64_rows` payload from
  `sys.stdin` instead of `sys.argv[2]`; the script now takes only `<db_path>` as an
  argument
- `transport/lifecycle.py` — `_inject_auth` switches from `container_exec_checked` to
  `container_exec_stdin`, passing `auth_b64` as the stdin payload
- `tests/unit/test_lifecycle.py` — new `TestInjectAuthStdin` test class asserting that
  `_inject_auth` uses `container_exec_stdin` and that the auth payload does not appear
  in argv
- `openspec/specs/secret-delivery-hardening/spec.md` — new requirement and scenarios
  covering stdin delivery for `inject_auth.py`

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `secret-delivery-hardening`: extend the existing spec with a new requirement that
  `inject_auth.py` SHALL receive its auth payload via stdin; the `b64_rows` value
  SHALL NOT appear in any element of the process argv

## Impact

- `transport/container_scripts/inject_auth.py` — interface change: `argv` shrinks from
  `[script, db_path, b64_rows]` to `[script, db_path]`; `b64_rows` read from stdin
- `transport/lifecycle.py` — `_inject_auth` call site: swap `container_exec_checked`
  for `container_exec_stdin`
- `tests/unit/test_lifecycle.py` — new test class; existing lifecycle tests unaffected
- `openspec/specs/secret-delivery-hardening/spec.md` — additive delta; no existing
  requirement text is removed
- No API surface changes; no database schema changes; no breaking changes to external
  callers
