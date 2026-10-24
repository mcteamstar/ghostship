## Context

See `proposal.md — Why` for motivation.

`_inject_auth` in `transport/lifecycle.py` currently calls:

```
podman.container_exec_checked(
    container,
    ["python3", f"{SCRIPTS_DIR}/inject_auth.py", KIRO_CLI_DB, auth_b64],
)
```

The `auth_b64` string is base64-encoded JSON of `[[key, value], ...]` kiro-cli SQLite
rows.  Because it is a positional argv element it appears verbatim in
`/proc/<pid>/cmdline` for the lifetime of the exec, making the kiro credential
readable by any process on the host that can access that pseudo-file.

`inject_policy.py` (TRN-260 H-1) addressed the same pattern for the HMAC signing key
by adopting `container_exec_stdin`.  The infrastructure (`container_exec_stdin` on
`PodmanClient`; `FakePodmanClient.container_exec_stdin` in the test harness) is already
in place.  `inject_auth.py` needs the same migration.

## Goals / Non-Goals

**Goals**
- `auth_b64` is delivered via stdin, not argv; never appears in `/proc/<pid>/cmdline`
- Script interface backward-compatible at the call site within the codebase (the only
  caller is `_inject_auth`; the script is internal to the transport image)
- New test assertions match the pattern already established by `TestInjectPolicyStdin`

**Non-Goals**
- `read_auth.py` — that script only reads from the DB, it produces no secret output
  into argv and is out of scope
- Changes to other `container_exec_checked` call sites not related to auth

## Decisions

### D-1: Mirror inject_policy.py exactly

`inject_policy.py` is the established precedent in this codebase.  The migration for
`inject_auth.py` mirrors it verbatim:

| Aspect | inject_policy.py | inject_auth.py (after) |
|--------|-----------------|------------------------|
| Caller | `container_exec_stdin(container, cmd, payload_b64.encode())` | `container_exec_stdin(container, cmd, auth_b64.encode())` |
| Script read | `sys.stdin.read().strip()` | `sys.stdin.read().strip()` |
| argv | `[script, crew_dir]` | `[script, db_path]` |

Alternatives considered: passing via environment variable (still visible in
`/proc/<pid>/environ`; ruled out) or a temp file inside the container (race condition,
cleanup burden; ruled out).

### D-2: No change to the `auth_b64` encoding

The payload is already base64 JSON.  There is no reason to re-encode it.  The stdin
read strips trailing whitespace before decoding, matching the `inject_policy.py`
pattern.

### D-3: Test mirrors TestInjectPolicyStdin

`TestInjectAuthStdin` in `test_lifecycle.py` follows the same structure as
`TestInjectPolicyStdin` (lines 756–831):

1. Assert `container_exec_stdin` was called (not `container_exec_checked`)
2. Assert the `auth_b64` value does not appear in any argv element
3. Assert `auth_b64` is present in the `stdin_data` bytes

Uses `FakePodmanClient` (already supports `container_exec_stdin`); no new fakes needed.

## Risks / Trade-offs

- **In-container compatibility** → `inject_auth.py` is bundled in the crew container
  image; the lifecycle.py caller and the container script must change together.  Because
  the only caller of `_inject_auth` is in `transport/lifecycle.py` and both files ship
  from the same repo at the same time, there is no version-skew window.  No migration
  needed.
- **stdin read blocking** → `container_exec_stdin` closes the write side after writing
  `stdin_data` so the script sees EOF.  `sys.stdin.read()` in the script blocks until
  EOF, which is guaranteed when the caller uses `container_exec_stdin`.  No deadlock
  risk (same guarantee already relied on by `inject_policy.py`).

## Migration Plan

All three files (`inject_auth.py`, `lifecycle.py`, `test_lifecycle.py`) ship together
in the same commit.  No staged rollout or feature flag required.  A plain forward
deployment of the transport image picks up all three changes simultaneously.

Rollback: revert the commit; both the container script and the lifecycle caller revert
to the argv pattern.

## Open Questions

None.
