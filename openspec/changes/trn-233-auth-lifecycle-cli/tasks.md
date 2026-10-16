# Tasks

Prerequisite: `trn-240-transport-refactor` is merged (its `LoginFlow`
classes are assumed below). Numbered groups go
in order; tasks inside a group may go in any order. Every task ends with
`pytest tests/unit/ -q` green.

## 1. Credential store

- [ ] 1.1 Add `transport/credentials.py` with `CredentialStore`
  (`get`/`put`/`delete`/`status`), backend/method validation and the JSON
  envelope (design §1). Writes use temp file + `fsync` + `os.replace` in
  `DATA_DIR/credentials/` (0700 dir, 0600 files), not TRN-240's
  truncating `_write_secret_file`. Records mask values in `__repr__`. Every read value goes
  through `_security.register_secret`. Verify: new
  `tests/unit/test_credentials_store.py` covers 0600 mode, atomic replace
  (simulated crash leaves old file), unsupported backend/method pair, one
  active credential per backend, and status containing no values.

## 2. Transport resolves credentials per launch

- [ ] 2.1 Replace the module-level credential globals in `tools.py` and
  `login.py` (`_ANTHROPIC_API_KEY`, `_CLAUDE_CODE_OAUTH_TOKEN`,
  `_OPENAI_API_KEY`, `KIRO_API_KEY`) with `store.get(backend)` in launch
  gating, env injection and `_finish_crew_setup` (design §4). Note: after
  TRN-242, credentials live in `transport/tools.py` (launch gating, lines
  ~270-280 and ~586-650) and `transport/login.py` (~112-116 and ~727-729).
  `transport/server.py` still has its own `_ANTHROPIC_API_KEY` etc. at
  ~458-465 and `KIRO_API_KEY` at ~643 — remove all of these. Remove the
  matching fields from `transport/config.py` and its `_SECRET_FIELDS`
  masking. Verify: add `tests/unit/test_credentials_launch.py` covering
  store-based launch gating (API key present → no flow started, no credential
  → flow started), credential rotation reaching the next launch with no
  restart, and that no module-level credential globals remain (`grep -rn
  "_security.get_secret.*api-key\|_security.get_secret.*oauth\|_security.get_secret.*openai"
  transport/tools.py transport/login.py transport/server.py` is empty after
  this task). Note: the test files referenced in the original plan
  (`test_trn226*`, `test_trn172*`, `test_trn170*`, `test_trn167*`,
  `test_trn171*`, `test_trn157*`) were deleted in TRN-244 — add fresh tests
  in the new DI style using `FakePodmanClient` and a temp-dir credential store.
- [ ] 2.2 Update `_warn_inert_backend_settings` (now in `transport/login.py`
  after TRN-242) to report stored credentials for disabled backends (by backend
  and method) and `*_BASE_URL` settings. Verify: updated inert-settings tests,
  including that values are not logged.

## 3. Transport auth API

- [ ] 3.1 Route table: register the `/login/{backend}/{method}`,
  `GET /login/{backend}` and `POST /logout/{backend}` routes from
  design §3 under bearer auth. Note: after TRN-242, the kiro/claude/codex
  HTTP handlers live in `transport/login.py` (not `server.py`); add the
  new routes there. Remove bare `POST /login`, `POST /logout`,
  `POST /login/claude`, `POST /login/claude/code` and `POST /login/codex`.
  Widen the rate-limit rule to `POST /login/*` and update the OpenAPI schema.
  Verify: route tests for 404 on an unknown backend or method, 401 without
  the bearer key, and the old paths (including bare `/login` and
  `/logout`) returning 404.
- [ ] 3.2 Pasted-secret routes (`api-key`, `setup-token`) store via the
  store and return status. Login routes return 400 for a disabled backend. `GET /login/{backend}` returns status and any
  pending flow (kiro also returns configured Identity Center defaults). `POST /logout/{backend}` clears the credential,
  cancels the flow, wipes running crews, and is idempotent. Verify: tests for
  store, empty-secret 400, status with no values anywhere, logout with and
  without a credential, and running-crew wipe.
- [ ] 3.3 `POST /login/kiro/builder-id` and `.../identity-center` drive
  `KiroLoginFlow`. Identity Center takes `{start_url?, region?}`, defaulting to
  `KIRO_IDENTITY_PROVIDER`/`KIRO_REGION`, adds `--license pro`, and returns 400
  if a value is still missing. `POST /login/claude/oauth` and `.../oauth/code`
  drive the Claude flow. Completion stores via the store (recording `provider`
  for Identity Center) and replaces any existing credential, so neither flow
  returns 409 because a credential exists. Verify: updated `crew-login` and
  claude login tests.
- [ ] 3.4 Rebuild Codex ChatGPT sign-in on `codex login --device-auth`
  (design §7). First run the command in a `ga-codex-login-*` container
  against a real account and save the output as a test fixture. If the
  bundled codex-acp binary lacks `--device-auth`, add a pinned `@openai/codex`
  install to `crews/spec-ops/toolchains/codex.sh`. Replace `codex-acp login`
  in `CodexLoginFlow`, store `auth.json` as method `chatgpt`, deliver it to
  crews as `~/.codex/auth.json`, and map "device code not enabled" to the
  documented error. Verify: flow tests built on the captured fixture
  (URL and code extracted, completion stores `chatgpt`, disabled-account
  error, 409 when pending, expiry), plus a launch test for `chatgpt`
  delivery.
- [ ] 3.5 Remove the `ga-codex-auth` helpers and the old `codex-acp login`
  path. Verify:
  `grep -rn "ga-codex-auth\|codex-acp\", \"login" transport/` is empty.

- [ ] 3.6 Launch with no stored credential starts the backend's interactive
  flow (kiro Identity Center if configured, else Builder ID; claude
  authorisation code; codex ChatGPT), reuses a pending flow, and returns
  `not_authenticated` with `login_url` and `code`. Update the MCP `launch` tool
  description to list the per-backend flows. Verify: launch-gate tests for
  each backend, for kiro with and without Identity Center configured, for the
  pending-flow reuse, and for an API-key credential starting no flow.

## 4. CLI

- [ ] 4.1 Shared URL and key discovery for every CLI subcommand: flag, then
  env (`GHOSTSHIP_URL`/`GHOSTSHIP_API_KEY`), then the installed port and
  `/data` mount source via Podman inspect (`ga-api-key` there), then the
  default (design §6). Add the HTTPS-or-loopback check with `--insecure`. Verify: `test_ghostship_auth.py` cases for each level, and a keyed
  install needing no flags, and refusing a secret over plain HTTP to a
  remote host.
- [ ] 4.2 `ghostship auth <verb> [backend]` dispatch with usage, the backend
  required for login and logout, and unknown verb or backend errors. Verify:
  dispatch tests, including `ghostship auth login anthropic` exiting non-zero
  without contacting the transport.
- [ ] 4.3 `auth login`: the method menu, `--method`,
  replacement confirmation with `--yes`, hidden-prompt and stdin secret
  reading, device and authorisation-code polling, and Identity Center prompts
  with `--identity-provider`/`--region`. Verify: tests for each spec scenario
  in trn-cli (piped secret, empty secret, no-tty-without-method, decline
  replace, timeout), plus a check that no secret appears in argv or stdout.
- [ ] 4.4 `auth logout <backend>` (`POST /logout/{backend}`) and
  `auth status` (table and `--json`). Verify: tests for the logout success and
  nothing-stored cases, and for the status table with no values.

## 5. Installer and uninstaller

- [ ] 5.1 Delete the backend credential secret blocks and compose lines,
  and credential alias mapping in `scripts/install.sh`
  (Kiro Identity Center settings and flags stay). Add the ignored-setting warning. Verify: replace `TestInstallSecretWiring` and
  `TestDeprecatedModelKeyNames` with tests asserting that install.sh contains
  no `secret create|rm` for the four names, that the warning fires for each
  ignored variable, and that the `*_BASE_URL` aliases still map.
- [ ] 5.2 Wizard: keep the Kiro Identity Center prompts, and drop the
  `auth login anthropic|openai` hints. After the transport is ready, offer
  `ghostship auth login <backend>` per unconfigured enabled backend, using
  the installed URL and key. Verify: wizard tests on `--wizard </dev/null`
  and a scripted tty run against a keyed install.
- [ ] 5.3 `scripts/uninstall.sh` keeps `credentials/` (`--purge-auth`
  removes it) and removes the four obsolete credential Podman secrets by
  name. Verify:
  uninstall tests for the default and purge cases on macOS and Linux paths.

## 6. Docs and config example

- [ ] 6.1 Remove the credential entries (not the Kiro Identity Center ones)
  from `config/ghostship.conf.example`, and replace them with a pointer to
  `ghostship auth login`. Verify: `test_config_sync.py` green.
- [ ] 6.2 Rewrite the auth sections of `docs/auth.md`, `docs/configuration.md`
  and `README.md` for `ghostship auth login|logout|status` and each
  backend's methods, plus a breaking-change upgrade note (log in again). Verify: no remaining
  `ANTHROPIC_API_KEY=`, `CLAUDE_CODE_OAUTH_TOKEN=` or
  `ghostship auth login anthropic` in docs (`grep -rn`).

## 7. End-to-end check

- [ ] 7.1 On a fresh local install with a bearer key, run
  `ghostship auth login` for kiro (Builder ID), claude (setup-token) and
  codex (ChatGPT, then API key). Check `ghostship auth status`, launch one crew per backend
  and dispatch a smoke task to each, then rotate the claude credential and
  confirm the next crew uses the new one with no restart. Re-run
  `install.sh --wizard` and confirm `ghostship auth status` is unchanged.
- [ ] 7.2 On an existing pre-change install, upgrade and confirm that the
  old Podman secrets and login files have no effect, and that the first
  `launch` per backend starts that backend's login (kiro Identity Center when
  configured). Completing it lets the next launch succeed.

## Workflow follow-up

- Archive after review. `retire_capabilities: true` deletes the emptied
  `claude-setup-token-auth` spec at archive time.
