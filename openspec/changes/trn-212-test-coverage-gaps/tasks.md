# Tasks: trn-212-test-coverage-gaps

## A. Install / Uninstall Script Tests

Resync the shell integration tests to call the real scripts via a sandbox
harness (see design.md D1).  Each group-A task is independently shippable
because it targets a self-contained test file.

- [ ] A.1 Write `tests/integration/helpers/sandbox.sh` — shared functions that
  create a tmpdir sandbox, place stub `podman` / `systemctl` / `id` binaries on
  `PATH`, export `HOME`/`PREFIX`/`XDG_DATA_HOME`/`XDG_RUNTIME_DIR` to tmpdir
  paths, and clean up on `EXIT`.

- [ ] A.2 Rewrite `tests/integration/test_install_config.sh` to source
  `helpers/sandbox.sh` and invoke `scripts/install.sh` directly for each test
  case.  Remove the `test_parse` / `test_parse_dedicated` reimplementations.
  Cover the flags that exist today: `--config`, `--identity-provider`,
  `--region`, `--license`, `--port`, `--model`, `--model-default`,
  `--public-url`, `--api-key`, `--caddy-domain`, `--caddy-tls-mode`.  Add a
  test case that asserts `--file-public-url` and `--mcp-public-url` are
  rejected as unknown flags (regression guard against re-adding them).

- [ ] A.3 Rewrite `tests/integration/test_uninstall_auth_preservation.sh` to
  source `helpers/sandbox.sh` and invoke `scripts/uninstall.sh --yes` directly.
  Replace the four `simulate_*` functions with assertions on filesystem state
  after the real script runs.  Keep the four existing scenarios: no
  `--purge-auth` (auth survives), `--keep-machine` (containers survive),
  `--purge-auth` removes auth, and data-dir cleanup.

- [ ] A.4 Add a test case to `test_uninstall_auth_preservation.sh` that runs
  `scripts/uninstall.sh --yes --purge-auth` and asserts `ga-kiro-auth` is
  absent — this is the regression that the current test would miss.

## B. Codex Login Unit Tests

New test class in a new file `tests/unit/test_trn212_codex_login.py`.  Covers
`_initiate_codex_login` internals directly (see design.md D2).

- [ ] B.1 Add `TestCodexLoginTOCTOUGuard` — two tests: (a) first call sets
  `_codex_login_pending` to `{state: "starting"}` and returns
  `{login_url, code}`; (b) a concurrent second call while the first is in
  flight returns `{login_pending: True}`.  Use `unittest.mock.patch.object` on
  `_lifecycle._codex_login_pending` to inject the in-flight state.

- [ ] B.2 Add `TestCodexBinaryProbe` — two tests: (a) `codex-acp` absent after
  10 probes → function returns `{error: "...codex-acp...not found..."}` and
  calls `_nuke_codex_login_container`; (b) `codex-acp` found on first probe →
  proceeds to PTY exec.  Mock `container_exec` to return `""` or
  `"/usr/local/bin/codex-acp"` as appropriate.

- [ ] B.3 Add `TestCodexPtyUrlExtraction` — use a socketpair (writer thread
  plays back `"Login URL: https://auth.openai.com/oauth?user_code=ABCD\n"`) to
  verify that `_initiate_codex_login` returns
  `{login_url: "https://auth.openai.com/...", code: "ABCD"}`.  Assert the
  writer thread is joined within 5 s.

- [ ] B.4 Add `TestCodexPtyTimeout` — writer thread sends no URL within 45 s
  (deadline patched to 0.2 s); verify function returns
  `{error: "...did not produce a login URL..."}` and nukes the container.

- [ ] B.5 Add `TestCodexContainerStartFailure` — `_start_codex_login_container`
  raises; verify `_codex_login_pending` is reset to `None` and function returns
  `{error: ...}`.

## C. PTY Helper Tests

Extend `tests/unit/test_pty_login_sequences.py` with a new test class for the
prompt-answer path of `_run_pty_login_flow`.

- [ ] C.1 Add `TestPtyPromptAnswer` — writer thread sends
  `b"Continue? "` (no URL), then after receiving `\n` sends
  `b"Open this URL: https://auth.example.com/login?user_code=XYZ\n"`.  Assert
  the returned URL equals `"https://auth.example.com/login?user_code=XYZ"` and
  the prompt was answered exactly once.

- [ ] C.2 Add `TestPtyPromptAnsweredOnce` — two `?` sequences in the output;
  assert the answer bytes are sent only once (the `answered` set deduplicates).

- [ ] C.3 Add `TestPtyCodeExtraction` — Codex URL patterns with
  `?user_code=WXYZ` in the URL; assert `login_code == "WXYZ"`.

- [ ] C.4 Add `TestPtyDrainThreadCloses` — after `_run_pty_login_flow` returns
  a URL, assert the writer-end socket is eventually closed (the drain thread
  reads to EOF).  Use a `threading.Event` set by the writer on close.

## D. Auth File Tests

New test class in `tests/unit/test_trn212_auth_files.py`.  All tests use
real tmpdir paths via `tempfile.mkdtemp` + `unittest.TestCase.addCleanup`.

- [ ] D.1 Add `TestWriteAuthFile` — calls `_write_auth_file(value, _path=tmpfile)`;
  asserts file content equals `value` and `stat().st_mode & 0o777 == 0o600`.

- [ ] D.2 Add `TestWriteAuthFileOverwrite` — calls `_write_auth_file` twice
  with different values; asserts second value is on disk and mode is still
  `0o600`.

- [ ] D.3 Add `TestWriteCodexAuthFile` — calls `_write_codex_auth_file(data,
  _path=tmpfile)` with byte payload; asserts content and `0o600` mode.

- [ ] D.4 Add `TestInjectCodexAuthChunking` — build a tar of `auth.json`,
  call `_write_codex_auth_file` to persist it, then call `_inject_codex_auth`
  with a mock Podman that records `container_exec` calls.  Assert: (a) `mkdir
  -p` called first; (b) `printf … >> /tmp/_ga_codex_auth.b64` called in
  chunks of ≤ 4096 bytes; (c) final `base64 -d … | tar -xf …` command
  issued; (d) round-tripping the base64 chunks reassembles the original tar
  bytes exactly.

## E. CI Integration Gate

- [ ] E.1 Add a `integration-tests` job to `.github/workflows/test.yml` that
  runs on `ubuntu-latest`, checks out the repo, runs
  `tests/run.sh --integration`, and is required for PRs targeting `main`.  No
  additional Python or Podman setup is needed — the bash scripts use only
  POSIX tools and stub binaries.

- [ ] E.2 Add `integration-tests` to the branch-protection required-status
  list in the repo settings (document the manual step in a comment in
  `.github/workflows/test.yml`).
