# Design: trn-212-test-coverage-gaps

## Context

See proposal.md for motivation. Code references are at `ee0b3b8`; line numbers
may drift.

Current test landscape (1 210 unit tests at review time, 0 integration tests in
CI):

```
tests/
  unit/                   # pytest, run by CI via tests/run.sh --unit
  integration/            # four bash scripts, run.sh --integration, hand-only
  e2e/                    # pytest, not in CI
```

The shell integration scripts (`test_install_config.sh`,
`test_uninstall_auth_preservation.sh`) self-contain their logic instead of
calling the real scripts.  Consequently:

- `test_install_config.sh` accepts `--file-public-url` / `--mcp-public-url`
  (flags that were removed) and is missing `--public-url`, `--model-default`,
  `--caddy-domain`, `--caddy-tls-mode` (flags that exist).
- `test_uninstall_auth_preservation.sh` would pass even if `uninstall.sh`
  deleted credentials, because it calls `simulate_linux_teardown` rather than
  the real script.

For Python gaps:

- `_run_pty_login_flow` is exercised in `test_pty_login_sequences.py` but only
  for no-prompt / no-code cases.  The prompt-answer path (writing a `\n` when
  `?` appears) is untested at the unit level.
- `_poll_codex_login_container` has direct unit tests in
  `test_codex_login_poll.py`, but `_initiate_codex_login` (the caller that owns
  the TOCTOU guard, container startup, binary-probe loop, and PTY exec) has no
  direct tests — every integration-level Codex server test patches the poll.
- `_write_auth_file` / `_write_codex_auth_file` mode (`0o600`), fsync, and
  chunk-reassembly for inject are covered for `_save_registry` (9.7 in
  `test_auth.py`) but not for the login credential files.
- CI uses only `tests/run.sh --unit`; the `--integration` category (bash
  scripts) never runs in CI.

## Goals / Non-Goals

**Goals:**

- Sync the install/uninstall shell tests to call the real scripts in a sandbox
  (stubbed `podman`, isolated `HOME`/`PREFIX`) so flag drift cannot go undetected.
- Add direct unit tests for `_initiate_codex_login` covering the TOCTOU guard,
  the binary-probe loop, and the URL/code extraction path.
- Extend `_run_pty_login_flow` unit tests to cover the prompt-answer path
  (socketpair feeding `?` output).
- Add unit tests for `_write_auth_file` / `_write_codex_auth_file` (0o600
  mode, fsync) and `_inject_codex_auth` (chunk reassembly, base64 round-trip).
- Add `--integration` to the CI test matrix so shell script tests run on every
  push/PR.

**Non-Goals:**

- E2E coverage of interactive Claude or Codex login (both require a human to
  paste or approve in a browser — noted as a known gap in the proposal).
- Argon2 / `get_secret` env fallback (low severity; tracked separately).
- WebSocket relay closure tests (covered under TRN-202 dashboard relay work).
- Branch coverage for `transport/` generally — this change targets the specific
  high-risk gaps named in the proposal.
- Production code changes, except extracting an already-modular inner function
  if needed to make it testable without further patching.

## Decisions

### D1 — Shell integration tests call the real scripts via a sandbox harness, not reimplementations

**Chosen:** Each shell test sets up a temporary `HOME`, places stub binaries
(`podman`, `systemctl`, `id`, etc.) on `PATH` earlier than the system copies,
then invokes `scripts/install.sh` / `scripts/uninstall.sh` directly.  Flag-drift
is caught because the test calls the real parser.

**Alternative considered:** Keep self-contained reimplementations and just fix
the flag list.  Rejected: reimplementations will drift again; calling the real
script is the only durable approach.

**Constraint:** `install.sh` tries to build images and start containers.
Stubbing `podman` to exit 0 (or echo expected output) suppresses the real
infrastructure steps while still exercising flag parsing, config sourcing,
and the validation/error paths under test.

### D2 — Codex login unit tests use socketpair + a writer thread, same pattern as test_pty_login_sequences.py

**Chosen:** `_initiate_codex_login` is tested by patching
`container_exec_pty_stdin` to return a socketpair.  A writer thread plays back
PTY output (URL line, prompt, etc.).  `container_exec` and container
lifecycle calls are mocked.  This isolates the function's own logic without
requiring a real Podman socket.

**Alternative considered:** Patch `_run_pty_login_flow` entirely.  Rejected:
that defeats the purpose — the proposal's finding is that patching the poll hid
the false-completion bug; we want the real helper to run.

### D3 — Auth file permission tests use a real tmpdir, not mocks

**Chosen:** `_write_auth_file` and `_write_codex_auth_file` are called with a
`_path` override pointing at a tmpdir file.  The test asserts
`stat().st_mode & 0o777 == 0o600` after the call.

**Alternative considered:** Mock `os.open` / `os.fchmod`.  Rejected: mocking
the OS calls doesn't verify the actual permission on disk.

### D4 — CI adds `--integration` as a separate parallel job, not a step in the existing `test` job

**Chosen:** A new `integration-tests` job in `.github/workflows/test.yml` that
runs `tests/run.sh --integration`.  It does not require Podman (the bash
scripts run with stub binaries) and can run on `ubuntu-latest` without
additional setup.

**Alternative considered:** Add `--integration` as a step after `--unit` in the
existing job.  Rejected: separation keeps failure signals distinct and avoids
time-coupling between the two suites.

## Risks / Trade-offs

- **Sandbox escapes** → `install.sh` sources config files and may use paths
  that leak into the real filesystem.  The sandbox harness must set `HOME`,
  `PREFIX`, `XDG_DATA_HOME`, and `XDG_RUNTIME_DIR` to tmpdir paths before
  invoking the script.  Teardown removes the tmpdir unconditionally.
- **Stub-binary coverage gap** → stubbing `podman` means we don't catch bugs
  that only surface when real Podman output is parsed.  This is acceptable:
  the goal is flag-drift detection, not full Podman integration.
- **Threading in Codex login tests** → socketpair writer threads must be joined
  with a finite timeout to avoid test hangs.  Use the same pattern as
  `test_pty_login_sequences.py` (5 s deadline, join with timeout).
- **fsync in CI** → `os.fsync` may be a no-op on tmpfs but won't fail.  The
  test verifies the call doesn't raise, not the durability guarantee.

## Migration Plan

No production deployment steps.  Changes are purely to `tests/` and
`.github/workflows/test.yml`.  Roll forward only; no rollback needed.

## Open Questions

None — all design decisions are resolved.
