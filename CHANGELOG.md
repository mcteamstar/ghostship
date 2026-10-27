# Changelog

## v0.9.0

### Base image bump to KiroCrew 0.10.0 (TRN-271)

- Crew image now extends `ghcr.io/kirodotdev/kirocrew:0.10.0` (multi-arch index digest `sha256:b6d0b9a3a666df30d99fcadc6a71ab83cbf4ed1c6521e1b81f0333c5553f3e90`, covering arm64 and amd64).
- kiro-cli bumped 2.32.0 → 2.34.0. Migration schema unchanged at (6, 5) — no `seed_kiro_db.py` logic changes needed.
- Re-run `./install.sh` to rebuild the crew image and pick up KC 0.10.0. Existing crews keep their current image until nuked and re-launched.

### Security hardening (TRN-272)

- **Per-session CSRF tokens** — `DashboardGate` now issues a unique `gs_csrf` nonce per session (cookie-echo pattern) instead of a single process-wide token. A forged or mismatched CSRF token returns 403 before the API key is evaluated.
- **XFF rate-limit bypass fixed** — `_caller_key()` in `auth.py` previously trusted `X-Forwarded-For` unconditionally. Clients could spoof the header to evade per-IP rate limiting. XFF is now only honoured from CIDRs listed in the new `GA_TRUSTED_PROXY_CIDR` config key; unauthenticated requests use the ASGI client address.
- **Login race (TOCTOU) fixed** — `login.py` login handlers for kiro, Claude, and Codex now hold the flow lock across the state-read → container-dereference window. A concurrent `abort()` could previously race between those two steps and dereference a nil container pointer.
- **Open-redirect NFKC normalisation** — `_validate_next_url()` now NFKC-normalises the `next` parameter before validation. Unicode lookalike sequences that bypassed the existing prefix/scheme guards are now caught.
- **`Secure` cookie flag on `gs_session`** — the session cookie now carries `Secure` when the transport's external URL is `https://`.
- **`GA_BATCH_MAX_TASKS` config error** — a non-integer value previously raised an uncaught `ValueError` at startup; it now raises a `ConfigError` with a clear message.

### Quality and correctness fixes (TRN-273)

- **`yaml_config.py` key injection guard** — `bin/install.sh` evals output from `yaml_config.py`. Key names are now validated against `[A-Z0-9_]+` before emission; a malformed YAML key can no longer inject shell.
- **`dispatch()` null `task_id` guard** — certain gateway error paths returned `{"task_id": null}` on what appeared to be a success path. Every non-error response from `dispatch()` now always carries a non-null `task_id` string; any error path returns `{"error": ...}`.
- **`verify_password` bare except narrowed** — `security.py` previously caught `Exception` broadly in `verify_password`, swallowing unexpected bugs. The except is now narrowed to argon2-specific exceptions.
- **`_REGISTERED_SECRETS` pruned on nuke** — the set of registered secrets in `security.py` was never pruned, so secrets from nuked crews accumulated indefinitely. `deregister_secret()` is now called from the nuke cleanup path.
- **Startup warning elevated on non-loopback bind** — when `GA_TRANSPORT_SECRET` is unset and the transport binds to a non-loopback interface, the startup log is now CRITICAL (was WARNING). A new `GA_REQUIRE_SECRET_ON_EXTERNAL_BIND` config key can be used to hard-fail instead of warn.

### Docs refresh (TRN-274)

- `docs/architecture.md`, `docs/configuration.md`: base image references updated to KC 0.10.0 / multi-arch digest `b6d0b9a3...`.
- `CHANGELOG.md`: this v0.9.0 section added.
- `docs/portal.md`: port range corrected from "1024 ports" to "64 ports default" (`GA_DASHBOARD_PORT_RANGE_SIZE=64`); firewall example corrected from `64058:65081` to `64058:64121/tcp`.
- `docs/configuration.md`: `CREW_GATEWAY_PORT` source file corrected to `transport/constants.py`; `KIRO_API_KEY` description updated (moved to credential store, not removed); `GA_DASHBOARD_PORT_RANGE_SIZE` added to configuration table; duplicate `PODMAN_SOCKET` entry removed.
- `docs/troubleshooting.md`: TRN-16 annotation updated to archived.
- `docs/release-notes-0.6.0.md`: stale `ghostship.conf` and `GA_AGENT_BACKENDS` references annotated.

### Unit test coverage (TRN-275)

- Added `tests/unit/test_server.py` — covers `_extract_crew_proxy_parts`, `_sanitise_query_string`, `_parse_ttl_seconds`, `_jwt_exp`, `_cookie_near_expiry`, and `_handle_health`.
- Added `tests/unit/test_dashboard.py` — covers `_validate_next_url` (open-redirect guard, NFKC, backslash, control characters), `DashboardGate` CSRF token uniqueness and forged-CSRF rejection, `gs_session` cookie flags (SameSite, Secure, HttpOnly).
- Unit test count: 912 → 975.

## v0.8.1

### Default agent model changed to `claude-haiku-5-5` (TRN-266)

- All six academy agent personas now default to `claude-haiku-5-5` (was `gpt-5.6-luna`). At 0.06× credits for requests up to 100K tokens, Haiku 5.5 is the most cost-efficient model available and a strong fit for high-volume agentic work.
- `model.default` in `config/ghostship.yaml.example` is set to `claude-haiku-5-5` so the intent is explicit even when no per-backend override is configured. Existing `backends.<b>.model.override` entries continue to win.

### Crew orchestration

- Added the `ghostship-spawn` Academy skill (TRN-263) for safe named-persona dispatch, task status, steering, and continuation through the crew gateway. Raven dispatches through the helper, so Captain autopilot no longer stalls on Claude crews because of hand-built gateway calls.

### Academy delivery (TRN-264)

- Academy skills, steering and MCP now reach every harness in the crew, not only kiro. At launch the transport stages them into `~/.agents/` and runs `.agents/setup`, which wires them into the native paths of every harness it detects in the image (for example `~/.claude/skills/` and `~/.claude/rules/` for Claude Code). Claude crews previously received none of the academy skills or steering docs.
- Agent personas (`academy/agents/*.json`) are still delivered to `~/.kiro/agents/` on every backend. That directory is KiroCrew's persona registry, which the gateway needs to resolve named dispatch on claude and codex crews as well as kiro.

### OpenSpec upgrade (TRN-265)

- Bundled OpenSpec CLI upgraded from `1.9.0` to `1.14.3` in the spec-ops crew image. All six `openspec-*` academy skills regenerated with the new version's templates.

### Claude crews

- Claude crews no longer add Claude Code attribution to commits or PRs: no `Co-Authored-By` trailer and no "Generated with Claude Code" PR text (TRN-262). The setting is baked into the image, so existing claude crews need relaunching after `ghostship upgrade`.

### Security (TRN-269)

- kiro-cli auth credentials are now delivered to crew containers over stdin rather than as a command-line argument. Previously the base64-encoded session token (~90-day lifetime) appeared in `/proc/<pid>/cmdline` inside the container and in Podman exec history on the host. The fix mirrors the pattern already used by `inject_policy.py`.

### Fixed

- `_schedule_monitor` and `_captain_monitor` now check for the `_NUKED_DURING_RESTART` sentinel before using the `_ensure_crew_running` result as a dict (TRN-268). Previously a nuke-during-restart race silently dropped the affected job for one cycle.
- `httpx.ReadTimeout` and `httpx.WriteTimeout` are now caught by the Phase 2 recovery path in `_crew_api_with_recovery` (TRN-268). Previously they escaped recovery, bypassed container restart, and surfaced as unformatted errors at the MCP tool boundary. (`httpx.TimeoutException` is used as the base class, covering `ConnectTimeout` as well.)
- `CredentialStore.get()` now logs a warning when a credential file contains corrupt JSON or an invalid base64 payload, instead of returning `None` silently (TRN-268).
- `install.sh` no longer fails with an unbound variable on macOS when the Podman machine name is not set during CA certificate extraction (TRN-268).
- When a crew gateway rejects a request and recovery gives up, the error now includes the gateway's HTTP status and response (redacted, up to 500 characters). Before, MCP callers saw only "crew … is unresponsive", even for a plain rejection such as `Agent 'ghost' not found`. A rejected request now says so, instead of suggesting a crew health check.
- `ghostship status` and the install output show the Caddy CA certificate path. Both looked up `ga-portal-data`, but Compose creates the volume as `ga_ga-portal-data`.
- Academy skills no longer carry Python bytecode (`__pycache__/`, `*.pyc`) into crews.
- Order templates tell Raven that a change's artifacts describe the target behaviour, so a change that rewrites Raven's own rules no longer makes Raven hold on a rule that isn't live yet.
- `_find_podman` now honours the dedicated socket for status URL detection.
- `ghostship status` uses `GA_HOST_URL` when no host port binding is present.

### Docs (TRN-267)

- `docs/architecture.md`: base image tag corrected to `ghcr.io/kirodotdev/kirocrew:0.9.0` (was `0.9.0-insider.4`).
- `docs/release-notes-0.6.0.md`: added a deprecation banner pointing to this changelog — that document's credential and config instructions are no longer current.
- `docs/portal.md`: dashboard port range size corrected to 64 (was incorrectly documented as 1024).

## v0.8.0

### ⚠ Breaking changes — read before upgrading

**1. Re-authenticate every backend after upgrading.**
0.8.0 removes the legacy `ga-kiro-auth`, `ga-claude-auth`, and `ga-codex-auth` credential files. After `ghostship upgrade`, existing crews will return `not_authenticated` until you log in with the new CLI. `install.sh` prints a prominent warning and prompts for confirmation when it detects an upgrade from <0.8.0.

```
ghostship auth login kiro
ghostship auth login claude   # if using claude backend
ghostship auth login codex    # if using codex backend
```

Recommended: `./uninstall.sh --purge-auth && ./install.sh` to start clean.

**2. Config file format changed: `ghostship.conf` → `ghostship.yaml`.**
`install.sh` auto-migrates an existing `ghostship.conf` on upgrade (old file kept as `.bak`). No manual action needed unless you have tooling that reads `ghostship.conf` directly.

**3. `network.host` now controls ga-portal's bind address only (default `127.0.0.1`).**
Previously `HOST=0.0.0.0` was the implicit default, making every install reachable from the LAN. If you rely on remote access: set `network.host: 0.0.0.0` (or a specific interface address) in `ghostship.yaml` **and** set `network.api_key` to protect it.

**4. `network.require_api_key` is deprecated — use `network.api_key`.**
A string value enables auth. `false` is the explicit no-auth opt-out. On any non-loopback `network.host`, no key causes `install.sh` to warn and abort.

**5. `ghostship auth logout <backend>` no longer touches running crews.**
Crews keep the credential they launched with until relaunched or nuked. This is intentional — logout is now transport-only. To drop a running crew's credential: nuke it and relaunch after logging back in.

---

### YAML config (ghostship.yaml) replaces ghostship.conf (TRN-253, TRN-257)

- YAML config uses semantic nesting: `network.tls.{certfile,keyfile}`, `crew.git.author.{name,email}`, `backends.default` (list), `backends.kiro.identity_center.{url,region}`, `portal.dashboard.port_range.{start,size}`, `portal.dashboard.default`, `machine.resources.{cpus,memory_mb,disk_gb}`.
- Three-layer merge: built-in defaults → `config/ghostship.yaml` → `~/.config/ghost-academy/ghostship.yaml` (XDG user override). Pass `--config <path>` to override both.
- Per-backend model precedence: `dispatch(model=...)` > `backends.<b>.model.override` > per-agent config > `backends.<b>.model.default` > `model.default` > built-in. `KC_MODEL_DEFAULT` and six `KC_MODEL_{BACKEND}_{OVERRIDE,DEFAULT}` env vars wired into `compose.yml`.
- `install.sh`, `start.sh`, and `uninstall.sh` all use the YAML config. `start.sh` no longer prompts for a `ghostship.conf` path when none exists.
- PyYAML bootstrapped automatically into `${TMPDIR}/ghostship-yaml-venv` on first use. `uv` is preferred; falls back to `ensurepip` + `get-pip.py`. No system Python contamination.

### Auth lifecycle and credential store (TRN-233)

- **`ghostship auth login <kiro|claude|codex>`** — interactive per-backend authentication. kiro: paste API key, Builder ID device code, or IAM Identity Center device code. claude: OAuth browser flow, paste API key, or paste setup-token. codex: ChatGPT device code or paste OpenAI API key.
- **`ghostship auth status`** — shows configured backends and stored credentials.
- **`ghostship auth logout <backend>`** — cancels any pending login and removes the stored credential. See breaking change #5 above for crew behaviour.
- Transport credential store (`transport/credentials.py`): one active credential per backend, 0600 files under `DATA_DIR/credentials/`. Credentials resolved per crew launch — rotation needs no restart.
- New transport auth API: `POST /login/{backend}/{method}`, `GET /login/{backend}`, `POST /logout/{backend}`.
- Installer no longer manages backend credential Podman secrets.

### Choose the backend per crew (TRN-259)

- **`launch` takes an optional `backend` argument** (`"kiro"`, `"claude"` or `"codex"`). Omit it and the crew uses the transport default as before. Different crews can now run different backends on one transport simultaneously.
- **Fix: restarts keep a crew's backend.** Reconcile and recovery restarts now use the crew's recorded `acp_backend` instead of the current transport default.

### Logout cancels pending login and leaves running crews alone (TRN-258)

- Logout returns `200 {"status": "logged_out"}` in every non-error case — no more 404 or 409 "not authenticated" responses. Returns `aborted_pending_login: true` when a flow was cancelled. Returns 500 only when a credential cannot be deleted.
- Fixed: logout during login container startup leaves no orphaned container; a new login starts immediately after a cancelling logout; a completing poll whose logout cancelled it stores no credential.
- **Fixed: kiro login completion no longer injects auth into claude or codex crews.** Auth injection on device login completion is now scoped to crews whose `acp_backend` is `kiro`.
- 409 responses from login POST routes now say `ghostship auth logout <backend>` instead of the raw REST route.

### `ghostship upgrade --skills` and skill management (TRN-255)

- `ghostship upgrade --skills` rebuilds images, restarts the transport, then re-runs `ghostship setup` to refresh skill symlinks and MCP registration.
- `ghostship setup` is the canonical command for registering the MCP server and installing skill symlinks. `ghostship skills` alias removed — use `setup` directly.
- `ghostship upgrade` prints a hint to add `--skills` when the skill version in the repo has advanced.

### Security hardening (TRN-260, TRN-235, TRN-211)

- **`inject_policy.py` HMAC key now delivered via stdin, not argv.** The policy signing key was passed as a command-line argument (visible in `/proc/<pid>/cmdline` on Linux). It is now written to the process's stdin via `container_exec_stdin`, matching the TRN-211 pattern.
- `hmac.new()` replaced with `hmac.HMAC()` in `transport/files.py` and `transport/container_scripts/inject_policy.py` (4 occurrences; deprecated since Python 3.4).
- `_inject_claude_auth`, `_inject_codex_auth`, and `_write_dashboard_cookie` use `container_archive_put` instead of `sh -c` / `python3 -c` (TRN-235).
- `Config` dataclass `__repr__` masks `kiro_api_key`, `anthropic_api_key`, `openai_api_key`, and `claude_code_oauth_token` to prevent credential leakage in logs (TRN-235).

### Bug fixes

- **`ghostship status` correctly reports `stopped` when the Podman machine is not running.** Previously showed "not installed" when the machine was stopped.
- **`nuke()` evicts per-crew in-memory state** (`_recovery_locks`, `_startup_generation`, `_crew_restart_outcomes`, `_idle_skip_reasons`) so nuked crew IDs don't accumulate in long-running transports.
- **Kiro Identity Center login fixes:** accept pre-filled Start URL / Region prompts with Enter; keep IDC defaults on `GET /login/kiro` while a device flow is pending; derive `--license` from login method, removing `backends.kiro.license` config.
- **Port range default corrected:** `ga_dashboard_port_range_size` dataclass default was 1024, should be 64 (matching YAML default and docs).
- `test_install_migration.sh` and `test_install_wizard.sh` added to `scripts/run.sh` integration suite (were silently skipped).

## v0.7.1

### KiroCrew 0.9.0 compatibility

This release pins ghostship to the KiroCrew **v0.9.0 stable** image (digest `sha256:a6156d268507...`, kiro-cli 2.32.0) and validates the full upgrade path from the insider pre-release. All breaking API changes introduced in the 0.9.0 insider line were addressed in the TRN-219–225 series (shipped in ghostship 0.7.1 pre-release commits); the stable cut adds no new breaking changes.

- **Base image bumped to v0.9.0 stable.** The crew image was previously pinned to `0.9.0-insider.4`. All five backport fixes between insider.4 and the stable tag (insider.5–9) are no-ops for ghostship: `auto_update=false` neutralises the wheel-fetch fix, no persona id conflicts the KAS reserved-id fix, and the MCP deferred-tool change only affects the internal worker scheduler. Migration schema verified unchanged: kiro-cli 2.32.0 ships the same 6 migrations (000–005) as 2.27.1; `seed_kiro_db.py` is correct as-is.

- **TRN-219 — crew image updated for KiroCrew 0.9.0.** Base image bumped from 0.8.0; `sandbox: "off"` and `sandbox_allow_unsandboxed_exec: true` added to `_patch_crew_config()` to satisfy the 0.9.0 Podman rootless sandbox gate. Node.js 24 LTS added to the spec-ops Containerfile (required by kiro-cli 2.27+). `kiro-cli DB pre-seeded` updated for migration schema 000–005.

- **TRN-220 — peer-cred guard on the internal gateway API does not affect ghostship.** KiroCrew 0.9.0 gates `X-Internal-Secret` / `X-Session-Key` requests by Unix socket UID. The transport authenticates exclusively via cookie + Origin on the external path. `_FORBIDDEN_INTERNAL_HEADERS` guard added to `_crew_api`; contract enforced by `tests/unit/test_trn220_crew_api_headers.py`.

- **TRN-221 — SEL key relocation to `$KIROCREW_HOME/trust/` is transparent.** No transport surface reads the SEL signing key. Grep audit confirmed zero pre-0.9.0 path literals; `test_trn_221_no_hardcoded_sel_path.py` guards against regression.

- **TRN-222 — workspace-app scoping change.** Crew config adjusted so workspace-scoped apps are correctly isolated per crew.

- **TRN-223 — knowledge auto-ingest is opt-in.** `auto_ingest: false` added to the crew config patch so crews do not auto-ingest workspace files on start.

- **TRN-224 — memory retrieval now ranks by vector similarity.** No ghostship code change needed. Operators of long-running crews with accumulated memory should expect task behaviour to shift on first start after upgrade; a one-time re-embedding pass may briefly delay startup. Fresh/ephemeral spec-ops crews are unaffected.

- **TRN-225 — memory pressure gate for cron spawns.** The gateway now gates cron-triggered spawns under memory pressure. The transport's `_crew_api` path is unaffected.

### Captain auto-pause via workspace sentinel (TRN-243)

Raven no longer loops indefinitely after completing a standing order. Previously, Raven's self-cancel curl (`POST /crews/{id}/captain/stop`) was blocked by `TransportSecretMiddleware` — crew containers cannot reach that endpoint by design.

The fix: Raven writes `.captain_done` into the workspace volume when satisfied. The captain monitor reads the file directly via the Podman archive API (no exec, no auth, no container required) and pauses the schedule. `captain(action="order")` clears the sentinel on new orders so the crew is reusable. Eliminates overnight admiral-mail storms from looping Raven runs.

### Shell exec hardening (TRN-235)

Three credential injection surfaces hardened against future injection:

- `_inject_claude_auth` and `_inject_codex_auth` base64-chunk appends replaced with `container_archive_put` (atomic tar write — structurally safe regardless of payload alphabet).
- `_write_dashboard_cookie` `python3 -c` f-string interpolation replaced with `container_archive_put`.
- `Config` dataclass gains `__repr__` masking for `kiro_api_key`, `anthropic_api_key`, `openai_api_key`, and `claude_code_oauth_token` so credentials never appear in logs.

### Lifecycle resilience (TRN-238)

- `_idle_monitor` lock scope reduced: `container_stop` now runs outside `_registry_lock`, with an in-flight flag preventing double-stop. Eliminates the 10–30s registry stall at higher crew counts.
- `_ensure_crew_running` leader checks for registry-entry removal by a concurrent `nuke()` after `container_start`, before proceeding with post-start setup.

### CSP fix for dashboard login page (TRN-237)

`DEFAULT_CSP` previously blocked the login page's own inline scripts under CSP Level 2+. Fixed with a per-response nonce: each `GET /dashboard/login` generates a `secrets.token_hex(16)` nonce, injects it into the HTML, and sets `Content-Security-Policy: script-src 'self' 'nonce-<n>'; style-src 'self' 'nonce-<n>'`. Inline script and style tags carry the matching nonce.

### Captain self-cancel fixed (TRN-241)

Two bugs in the Raven self-cancel flow (superseded by TRN-243 sentinel, but fixed independently):

- `KIROCREW_CREW_ID` was not injected into the crew container env, producing an empty path segment in the self-cancel URL. Fixed in `_finish_crew_setup` via `_patch_crew_config`.
- `POST /crews/*/captain/stop` was not in `TransportSecretMiddleware`'s public-route bypass list and received 401 before the cookie auth ran.

### Transport modularisation (TRN-240, TRN-242)

`server.py` split from a ~5000-line monolith into focused modules with no behaviour or API changes:

- `transport/tools.py` — all 10 MCP tool implementations (`crews`, `launch`, `supply`, `evac`, `nuke`, `dispatch`, `steer`, `pickup`, `schedule`, `captain`).
- `transport/captain_engine.py` — captain/schedule dispatch logic (`_dispatch_captain_checkin`, `_steer_captain_checkin`, `_captain_do_order/status/stop`).
- `transport/login.py` — kiro/claude/codex HTTP login/logout handlers.
- `transport/server.py` — HTTP infrastructure, routing, and middleware only.

Circular imports resolved by deferring `lifecycle` imports inside functions. All existing tests pass unchanged.

### Interactive installer wizard (TRN-233 partial)

`install.sh` gains a guided setup wizard on first install (no `ghostship.conf` present). Walks through backend selection, collects non-secret config, writes `ghostship.conf`, then builds, authenticates, and offers harness registration. Force it any time with `./install.sh --wizard`. Subsequent plain runs are non-interactive as before.

### Unit test suite rewrite (TRN-244, TRN-245, TRN-246, TRN-247, TRN-248, TRN-249)

The unit test suite was rewritten around dependency injection and a `FakePodmanClient` test double:

- Module-level globals eliminated in favour of explicit arguments; patches no longer need to track which module namespace a name was imported into.
- `tests/fakes.py` — `FakePodmanClient` with configurable container/exec/archive/secret stubs.
- `tests/unit/test_captain.py` — standing orders, scheduling, stop/resume, mail, cookie injection.
- `tests/unit/test_lifecycle.py` — `_ensure_crew_running`, launch/nuke, reconcile loop, memory gate, `_finish_crew_setup`.
- `tests/unit/test_caddy.py` — dashboard login, session auth, crew route lifecycle.
- `tests/unit/test_auth.py` — bearer middleware, HMAC, evac/supply presigned tokens.
- `tests/unit/test_monitors.py` — idle monitor, schedule monitor, captain sentinel branch, cookie refresh.

### Other fixes

- `GA_REQUIRE_API_KEY` now defaults to `error` on non-loopback installs (TRN-231). Installations reachable from non-loopback addresses with no API key configured log an error and refuse to serve at startup.
- Raven self-cancel endpoint corrected to `ga-transport:64057` (was `localhost:64057`, unreachable from inside a crew container).
- `trn-233` wizard: fixed `set -e` abort on non-tty stdin during guided setup.

## v0.7.0

### Breaking changes

- **Removed `POST /login/claude/setup-token` (TRN-226).** The route could never complete. `claude setup-token` asks for an interactive browser approval and prints its token to stdout; it does not write `~/.claude/.credentials.json`, which the route waited for. The route also ran blocking work on the transport's event loop, so a single call hung every other request until the transport was restarted. The route now returns 404. To migrate, run `claude setup-token` on your own machine, set `CLAUDE_CODE_OAUTH_TOKEN="<token>"` in `ghostship.conf`, and re-run `ghostship install`.

### Deprecations

- **Model backend settings use their standard names (TRN-226).** `GA_CREW_ANTHROPIC_API_KEY`, `GA_CREW_ANTHROPIC_BASE_URL`, `GA_CREW_OPENAI_API_KEY` and `GA_CREW_OPENAI_BASE_URL` are now `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `OPENAI_API_KEY` and `OPENAI_BASE_URL`, the names the Claude and Codex CLIs read. The old names still work from `ghostship.conf`, with a warning at install; when both are set, the new name wins. Values exported in the shell running `install.sh` are ignored under either name. The Podman secret names are unchanged, so existing installs need no migration beyond renaming the lines in `ghostship.conf`.

### Features

- **Headless Claude auth with `CLAUDE_CODE_OAUTH_TOKEN` (TRN-226).** The long-lived token from `claude setup-token` is now set in `ghostship.conf`, delivered as the `ga-claude-code-oauth-token` Podman secret, and injected into Claude-backend crews as `CLAUDE_CODE_OAUTH_TOKEN`. Every crew uses the same token, so the OAuth refresh-staleness limitation (see v0.6.0) does not apply. Each Claude crew gets exactly one credential, in this order: `ANTHROPIC_API_KEY`, then `CLAUDE_CODE_OAUTH_TOKEN`, then `ga-claude-auth`. See [docs/auth.md](docs/auth.md#claude-headless-auth-recommended).

### Fixes

- **API keys now suppress stored OAuth credentials as documented (TRN-226).** `transport/lifecycle.py` read `KIRO_API_KEY` and the Anthropic and OpenAI API keys from environment values that are always empty in production (the keys exist only as Podman secrets). As a result, a crew with an API key still received `ga-kiro-auth`, `ga-claude-auth` or `ga-codex-auth` alongside it. Both `server.py` and `lifecycle.py` now resolve all crew credentials from their secrets through `security.get_secret`, and the inert-setting warning checks the resolved values.
- **`install.sh` ignores the invoking shell's environment for every setting.** Fifteen settings had no built-in default, so a value exported in the operator's shell (for example `HOST`, the Anthropic base URL, `GA_RATE_LIMIT_ENABLED` or `GA_DASHBOARD_DEFAULT`) reached the transport without being in `ghostship.conf`. All now have defaults equal to their previous fallbacks, so the documented precedence (built-in default, then config file, then CLI flag) holds.

## KiroCrew 0.8.0 → 0.9.0 upgrade

- **TRN-220 — internal-API peer-cred validation (PR #2424) does not affect ghostship; transport uses the cookie path. Guardrail test added.** KiroCrew 0.9.0 (`0.9.0-insider.4`) adds unix-socket peer-credential validation to the gateway's internal-secret API path (`X-Internal-Secret` / `X-Session-Key`): a caller whose OS UID differs from the gateway's `kirocrew` process is now rejected even with a valid shared secret. The transport authenticates to crew gateways on the external dashboard-cookie path only (`Cookie` + `Origin`), so this is a no-op for ghostship today. `transport/lifecycle.py::_crew_api` now documents the invariant, carries `_FORBIDDEN_INTERNAL_HEADERS`, and refuses the internal-secret headers if a caller ever passes them via `headers=`; `tests/unit/test_trn220_crew_api_headers.py` asserts the cookie-only contract so a future change that routes an internal-API call across the UID boundary fails loudly in CI.

- **TRN-221 — SEL signing key moved to `$KIROCREW_HOME/trust/` (PR #2421 / issue #1881) does not affect ghostship. Convention pinned + guardrail test added.** KiroCrew 0.9.0 (`0.9.0-insider.4`) relocates the Security Event Log (SEL) signing key into the new consolidated `$KIROCREW_HOME/trust/` root. The SEL key is a gateway-internal credential; no ghostship transport surface reads, signs with, or verifies against it, so the upgrade works unchanged (behaviour change / low impact — no code change required). A grep audit of `transport/` against the target image confirmed zero SEL-key references (the only hits are the SQL `SELECT` keyword, `session_key_is_attested()`, the `_RAVEN_SELF_CANCEL` text, and the unrelated `.local_secret` docstring). The `$KIROCREW_HOME/trust/` convention for any future SEL-reading feature is documented in [docs/auth.md](docs/auth.md) ("Admiral mail signing"), and `tests/unit/test_trn_221_no_hardcoded_sel_path.py` fails CI if a pre-0.9.0 SEL path literal (`sel_key` / `sel.key` / `/sel/`) is ever reintroduced under `transport/`.

- **TRN-224 — memory retrieval now ranks by vector similarity, not recency (upstream PR #3243). Behaviour change / low impact — no ghostship code change required.** KiroCrew 0.9.0 (`0.9.0-insider.4`) embeds memories at write time and ranks them at retrieval by cosine similarity of the stored vectors against the current turn, replacing 0.8.0's recency ordering. **Operators of long-running crews with accumulated memory should expect task behaviour to shift after the upgrade**, because a different set of memories may be selected for injection into a given turn. The first start after upgrading a crew that already holds pre-0.9.0 memory rows may run a **one-time re-embedding pass** to backfill vector representations, which can briefly delay that first startup on large memory stores (a one-time cost; subsequent starts are unaffected). **Fresh and ephemeral crews (e.g. the spec-ops crew, which starts per-project with no accumulated memory) are unaffected by both the ranking change and the re-embedding pass.** Ghostship touches memory in exactly two places and neither needs changing: `transport/lifecycle.py::_patch_crew_config()` enrolls each agent with `"memory_store": "default"` (a store *selector* carrying no ordering assumption — still valid under 0.9.0), and `crews/_base/graduation/seed_kiro_db.py` seeds only `auth_kv` / `history` / `migrations` / `state` (verified `SELECT COUNT(*), MAX(version) FROM migrations` → `(6, 5)`), creating no `memories` / `lessons` / embedding table — those remain owned by the gateway's own first-start migration.

## v0.6.0

### Breaking changes

- **Retired `GA_INCLUDE_CLAUDE_AGENT` and `GA_INCLUDE_CODEX_AGENT` (TRN-202)** — agent backends are now enabled with one list, `GA_AGENT_BACKENDS` (for example `GA_AGENT_BACKENDS=claude,codex`; kiro is always available and is the default when unset). `install.sh` derives the image toolchains from this list. If either retired variable is set, the transport and `install.sh` fail at startup with a message naming `GA_AGENT_BACKENDS`. Migrate by replacing `GA_INCLUDE_CLAUDE_AGENT=true` with `GA_AGENT_BACKENDS=claude` and `GA_INCLUDE_CODEX_AGENT=true` with `GA_AGENT_BACKENDS=codex` (or list both).
- **Removed `prewarm` MCP tool and `POST /crews/{crew_id}/prewarm` REST route (TRN-194)** — the explicit prewarm surface is gone. Callers of `prewarm(crew_id=...)` will receive a tool-not-found error; `POST /crews/{id}/prewarm` returns 404. Warming is now internal: when `GA_PREWARM_ENABLED` is on (default `false`), it runs as a background side-effect of `supply` and `schedule`. `install.sh` does not pass `GA_PREWARM_*` through yet, so on a standard install warming is off.

### KiroCrew 0.6.0 → 0.8.0 upgrade (TRN-166, TRN-173, TRN-185, TRN-188)

Crew base image bumped from `0.6.0` to `0.8.0` (by way of `0.7.2` and `0.8.0-insider.8`). KiroCrew 0.7.x tightened the spawn security model — internal spawns now require attested session identities, and several schema and config changes were needed:

- `seed_kiro_db.py` updated for kiro-cli 2.24.0: 6 migration rows (versions 0–5), `state.value` changed from `BLOB` to `TEXT`, and removed `conversations`, `conversations_v2`, and `extracted_kas_versions` tables that no longer exist in 0.7.2.
- `KC_BASE_IMAGE`: the admission Containerfile's `ARG` default is the single source of the base image. `install.sh` passes `--build-arg KC_BASE_IMAGE` only when the config sets it.
- Transport/Caddy readiness timeout increased to 90s; health probe gains an exec+curl fallback for remote deployments.
- Auth polling fix: `launch` now polls the auth DB when login is pending — no longer requires `GET /login` to unblock the wait loop.

### Captain-driven spawning restored (TRN-185, TRN-186, TRN-187)

KiroCrew 0.7.0's attestation requirement broke the full Captain workflow (SDD, independent-review) — headless Raven tasks had no session identity and `/api/spawn` returned `member_identity_unavailable`. Fixed end-to-end:

- **Persona enrollment (TRN-186)** — `_patch_crew_config()` now writes a `config.agents` section for all 6 composition personas at crew launch. `_enroll_crew_members()` calls `POST /api/members/{slug}/thread` for each agent after gateway-ready, creating a DM binding and a member session identity. `enrolled_agents` is persisted in the crew registry across all three launch paths (fresh, stale-config restart, reboot recovery).

- **Member-based dispatch (TRN-187)** — `_resolve_dispatch_slot()` is the new unified helper for both single and batch dispatch. Enrolled persona agents automatically route into their `member-<slug>` parent session (attested identity), echoed back to the caller as the clean agent name (e.g. `"ghost"`, not `"member-ghost"`). Crews without `enrolled_agents` fall back to the previous bridge/headless behaviour.

- **Raven attestation** — Raven's spawn curl updated to send `X-Session-Key: $KIRO_SESSION_ID`. Both `spec-driven-development.md` and `independent-review.md` order templates updated to match.

### Dashboard auth hardening

Bearer auth removed from crew UI paths (`/crews/*/ui`, WebSocket). `Caddy` forward-auth (`gs_session` cookie) is now the sole gate for dashboard access — bearer tokens are no longer needed or accepted on those paths. `_dispatch_public_route` in `auth.py` gains glob pattern matching to support the `/crews/*/ui` path shape.

### New ACP backends

- **Claude Code (TRN-167)** — Claude Code ACP backend support. Crew containers can now run Claude Code as the underlying agent runtime alongside kiro-cli.
- **Codex (TRN-172)** — Codex ACP backend. `POST /logout/codex` returns 200 when already unauthenticated (idempotent).
- **Claude subscription OAuth (TRN-170)** — OAuth login flow for Claude subscription accounts. Three Banshee review fixes applied post-implementation.
- **Anthropic endpoint override (TRN-171)** — `GA_CREW_ANTHROPIC_BASE_URL` points Claude-backend crews at a custom Anthropic-compatible endpoint.

### Codebase cleanup (TRN-174, TRN-175, TRN-176, TRN-177, TRN-178, TRN-179, TRN-180)

- `KC_BASE_IMAGE` moved from module-level constant to `cfg.kc_base_image` (TRN-174)
- `_validate_claude_api_key` deleted; `Config.validate()` is now a no-op (TRN-175)
- Dead `inject-git-identity` code removed (TRN-176)
- Stale `ga-net` migration shim and docstring references removed (TRN-177)
- PTY login flow extracted to `_run_pty_login_flow` helper (TRN-178)
- Dead `GA_PORTAL_ENABLED` branches removed from dashboard-auth and TLS specs (TRN-179)
- `GA_DASHBOARD_PORT_RANGE_SIZE` env var wired into config (TRN-180)

### Dashboard WebSocket fixed (TRN-189, TRN-191)

Two bugs prevented the KiroCrew dashboard from establishing a WebSocket connection through the Caddy proxy:

- **Caddy WS forward_auth bypass (TRN-189)** — WebSocket upgrade requests were hitting the forward_auth gate and being rejected with 401. Caddy crew server config now emits two routes per crew: a WS upgrade route (no forward_auth) and an HTTP catch-all (with forward_auth). WebSocket sessions connect without authentication friction.

- **WS origin + auth.py dispatch (TRN-191)** — Three-bug chain: `BearerAuthMiddleware.__call__` was looking up the WS handler in `_routes` instead of `_public_routes`, so the handler was always `None` → 403. The transport WS proxy was sending `Origin: http://gs-{crew_id}:5476` but the gateway only accepts loopback; changed to `http://localhost:{CREW_GATEWAY_PORT}`. Together these fixes make `101 Switching Protocols` reliable — Ghost sessions stream live and sub-agents spawn correctly through the dashboard.

### Dispatch slot model simplified (TRN-192)

With member-based dispatch (TRN-186/187) working correctly, the `slot` parameter on `dispatch()` has been reduced from four modes to two:

- **`slot=None` (default)** — enrolled persona agents route into their attested member DM slot (`member-<slug>`), visible in the dashboard sessions list and able to make downstream spawn calls. Unenrolled agents dispatch headless.
- **`slot=False`** — explicit headless, regardless of enrollment. No session is created, saving ~250 MB RSS per dispatch.

`slot=True` (UUID auto-generation), `slot="bridge"`, and arbitrary named slots are removed. They were not attested (breaking downstream spawning for enrolled agents), cost the same memory as member slots, and offered no advantage now that member slots provide browser visibility for free. The bridge fallback for unenrolled agents on dashboard crews is also removed — unenrolled agents always dispatch headless.

`_resolve_dispatch_slot` in `lifecycle.py` is now three lines. `slot_pre_create` calls (which POSTed to `/api/chat/slots` before dispatch) are removed — member DM slots are pre-created at enrollment time. The `task_slots` field is removed from batch dispatch responses.

### Dashboard login redesign (TRN-190)

`GET /dashboard/login` rewritten with Ghostship's visual identity:

- Purple primary button (`#7c3aed`, hover `#6d28d9`) replacing the previous green
- Floating ghost emoji hero (👻) with CSS `translateY` animation above the form title
- Show/hide toggle on the API key field (inline SVG eye icon, vanilla JS)
- Shake animation on the error paragraph for failed login attempts
- Card widened to 360px with tightened label/field spacing
- Accessibility: `aria-hidden` on decorative elements, `role="alert"` on the error paragraph
- All CSS/JS inline — no external dependencies

### Known limitations

- **Captain autopilot on Claude backend (resolved in v0.8.1).** At this release, Raven could not use the gateway's local IPC secret; v0.8.1 delivers `ghostship-spawn` for cookie-authenticated persona dispatch. Relaunch an existing crew after upgrading so it receives the helper and refreshed Raven prompt.
- **Claude OAuth credentials go stale after the first token refresh.** Each crew receives a copy of `ga-claude-auth`. About eight hours after login, the first crew to run refreshes the token inside its own container, and later crews fail with "OAuth session expired and could not be refreshed". Work around it by logging in again (`POST /logout/claude`, then `POST /login/claude`) or by using `GA_CREW_ANTHROPIC_API_KEY`.
- **The default install is not authenticated.** `ga-portal` is published on all interfaces at `PORT` and `GA_API_KEY` is empty by default, so anyone who can reach the host can use every MCP tool. Set `GA_API_KEY` on any machine reachable from another host.

### Fixes

- **Logout reached Caddy, not the transport.** `POST /logout/claude` and `POST /logout/codex` were not routed to the transport, and Caddy answered them with an empty 200. They are now proxied like `/login*`.
- **Codex login completed without a credential.** Any non-empty file under `~/.codex/` counted as a finished login. Completion now requires a non-empty `auth.json`, as the Claude flow requires `.credentials.json`.
- **Login and logout reported success after a failure.** A failed credential write now returns 500 and keeps the login retryable instead of discarding the credential. A failed logout delete returns 500, the kiro logout audits only after the delete, and crews whose credential wipe failed are listed in the response.
- **Model API keys in `compose.yml`** are no longer world-readable: the file is written with mode 600.
- **Idle reaper:** one failing crew no longer ends idle reaping for the process, and the reason a crew is kept running is logged when it changes.
- **`install.sh`:** a flag given without a value now errors instead of exiting silently, an unknown `GA_PORTAL_TLS_MODE` fails fast, a line break in `GA_AGENT_BACKENDS` is rejected (matching the transport), and the migrated temporary config copy is removed on exit.
- **Config:** `nan` and `inf` are rejected for numeric settings.
- **Dashboard login:** a backslash in `next` (`/\evil.com`) can no longer redirect off-site.
- **Logs:** raw `kirocrew token` output is no longer logged when a token can't be parsed.

- **Presigned URL auth (TRN-169)** — `/files/?sig=` paths now exempt from Caddy bearer check; previously a presigned download through the Caddy proxy was incorrectly rejected with 401.

---

## v0.5.1

### evac pack=True

`evac` gains a `pack: bool = False` parameter. When `True`, the presigned URL streams a tar archive of the named directory instead of a single file — the complement of `supply(unpack=True)`. Useful for evacuating multi-file output directories, generated reports, or any non-git subtree from a crew workspace.

```bash
# Extract a directory
curl -s "$(evac path=subagent_output pack=True)" -o output.tar
```

### Documentation refresh and demo

README pitch tightened and a demo GIF added showing the full lifecycle: launch three crews, close the session, come back later, pick up results, nuke.

---

## v0.5.0

### KiroCrew 0.6.0

Crew base image bumped from `0.6.0`. Login containers also updated. `KC_BASE_IMAGE` config knob removed — login containers always match the crew image version and are no longer separately configurable.

### Dependency uplift

- `mcp[cli]` 2.0.0 → 2.2.0
- `croniter` 3.0.3 → 6.2.4 (transferred to pallets-eco)
- `httpx-ws` (single-maintainer) replaced by `websockets>=13.0,<15.0` (python-websockets org, 5700 stars); `httpx` compat shim removed
- `unittest-parallel` (single-maintainer) replaced by `pytest>=8.0.0,<9.0.0` + `pytest-xdist>=3.5.0,<4.0.0` (pytest-dev org)
- New dependency provenance policy: runtime deps require organisational backing

### Security fixes

- `_mail_count()` in `captain.py` — mailbox path now passed as a positional `$1` arg to `sh -c` instead of being string-interpolated, eliminating a latent shell injection vector
- CRLF injection in 301 redirect Location header — `host` and `path` components now stripped of control characters alongside the existing `qs` sanitisation

### Config fixes

- `GA_PORTAL_TLS_MODE` default corrected to `"off"` — was incorrectly defaulting to `"internal"` in `config.py` while all documentation and install scripts specified `"off"`

### Test coverage

- New tests for `cmd_status`, `cmd_stop`, `cmd_setup` ghostship CLI subcommands

---



### Fixes

- **Device-flow login completion falsely detected from the OIDC registration precursor** — `_read_auth_from_crew` treated *any* non-empty `auth_kv` row as proof a login had completed, including `kirocli:odic:device-registration`, which kiro-cli writes the instant the device flow starts, before the user has approved anything. Under fast polling, `GET /login` could report `complete` — and inject that precursor-only capture into every running/newly-launched crew — well before the actual OAuth grant existed, leaving crews with a stored "auth" that still fails kiro-cli's own login check (`AcpAuthRequired`). Fixed by requiring a real credential row (anything beyond the registration precursor) before treating a login as complete.

- **`ghostship auth login` errored instead of no-op when already authenticated** — the transport reports "already authenticated" as a `409` with a plain-text body, not the `{"status": "complete"}` JSON shape `auth_login`'s happy path checked for, so the CLI's only reachable behaviour was a hard error requiring a manual `logout` first. `auth_login` now recognises the 409 "already authenticated" body and treats it as a successful no-op; a genuinely different 409 (e.g. a concurrent login already in progress) still errors as before.

### Tests

- New unit coverage for `_read_auth_from_crew`: returns `None` when only the device-registration row is populated (the exact shape observed live), returns the payload once a real credential row joins it.
- Rewrote `ghostship auth login`'s 409-handling tests: the "already authenticated" 409 is now asserted as a no-op success; a new test covers a different 409 reason (login already in progress) still erroring correctly.

## v0.4.0

### New features

- **`ghostship auth login` / `ghostship auth logout` (TRN-150)** — CLI subcommands for the device auth flow. `auth login` initiates the flow, prints the URL and code, and polls until complete. `auth logout` revokes the current session. Both accept `--url` and `--api-key` flags for non-default or remote transports. No new dependencies — stdlib only (`urllib.request`).

- **`GA_DASHBOARD_DEFAULT` config flag (TRN-148)** — sets the default value of the `dashboard` parameter on `launch`. When `GA_DASHBOARD_DEFAULT=true`, every `launch()` call that omits `dashboard` gets a dashboard port allocated automatically. Explicit `True`/`False` always wins. Useful for academies where you always want dashboards without updating every call site.

- **Dispatch slot parameter (TRN-147)** — replaces the `mode` parameter with `slot: str | bool | None`. Controls which KiroCrew dashboard session a dispatched task is attached to:
  - `slot=None` — headless (no session); default when the crew has no dashboard
  - `slot="bridge"` — attach to the shared `bridge` slot; default when the crew has a dashboard
  - `slot=True` — auto-generate a unique slot name per task
  - `slot="<name>"` — attach to a named slot
  - The slot is pre-created via `POST /api/chat/slots` before dispatch (409 treated as success).

- **Auto-prewarm at launch (TRN-131)** — `_prewarm_crew()` fires at the end of `_finish_crew_setup`, sending `GET /api/ready` to warm the ACP session before the first real task arrives. Non-fatal — a prewarm failure is logged but does not fail the launch. `pre_warm_status` in the launch response. New env vars: `GA_PREWARM_ENABLED`, `GA_PREWARM_TTL_SECS`.

- **Docs infographics + tool docstrings (TRN-66)** — 3 new infographic PNGs (architecture, usage flow, fleet hierarchy). All 10 `server.py` MCP tool docstrings updated with workflow framing. README and docs reduced by ~30% via a targeted clarity pass.

### Fixes

- **Registry batch lookup subset match (TRN-151)** — `_find_batch_by_task_ids` previously required exact set equality, so a caller with a partial task list (lost or replaced tasks) could never resolve the batch and pickup stayed pending forever. Changed to subset match: if all provided `task_ids` are members of a batch, the batch is returned. Unit tests cover exact match, subset, superset (no match), and disjoint (no match).

- **`_ensure_crew_running` waiter race (TRN-152)** — when the leader's restart raised (memory gate, active-crew limit, gateway-not-ready), `finally` still set the Event but registry status was not reliably corrected. Waiters read stale `"running"` status and proceeded against a crew the leader had just failed to start. The leader now records an explicit success/failure flag on the Event; waiters read it and propagate the error rather than proceeding blindly.

- **`podman.py` hygiene (TRN-154)**:
  - Bare `except Exception: pass` narrowed to expected HTTP statuses (404/409) across `container_stop`, `container_remove`, `volume_create`, `volume_remove`, `secret_remove`, `network_disconnect`, `network_rm`, and worker cleanup. Real socket/permission failures now propagate or log at WARNING instead of being silently swallowed.
  - httpx2 sync and async clients are now closed via the uvicorn lifespan shutdown hook instead of module-level atexit (the event loop is gone by atexit time for async clients).
  - `container_exec` response closed via `try/finally` — httpx2 `Response` has no context manager protocol.
  - Raw sockets in `container_exec_pty_stdin` / `container_exec_stdin` wrapped in `try/finally` to prevent fd leak on header-phase raise.

### Tests

- **TLS context factory tests (TRN-153)** — new `tests/unit/test_tls.py` covering `_ssl_context_factory`: TLS disabled (no cert/key), TLS enabled with valid cert/key, TLS 1.2 minimum floor enforced, missing cert file raises.
- **`TransportSecretMiddleware` tests (TRN-153)** — passthrough when secret not configured, correct header passes, wrong header → 401, missing header → 401, constant-time compare verified.
- **`_ensure_crew_running` + recovery engine tests (TRN-152)** — new unit tests for `_crew_api_with_recovery` and `_phase0_transient_503` / `_phase1_stale_cookie` / `_phase2_dead_gateway` helpers: transient 503 retry, stale cookie refresh, dead-gateway restart, and leader-failure propagation.

### Docs

- **Docs consolidation** — 13 → 8 docs files: `caddy.md` + `dashboard-proxy.md` merged into `portal.md`; `security.md` merged into `auth.md`; `remote.md` folded into `configuration.md`; `reference.md` removed.

### httpx → httpx2 migration

`encode/httpx` went unmaintained in early 2026; Pydantic picked up stewardship under the `httpx2` package name. All 5 transport modules and all test files now use `import httpx2 as httpx`. The old `httpx` package is kept pinned in `requirements.txt` solely for `httpx-ws` until it adds `httpx2` support.

### Other

- Dashboard port range hardcoded to 1024 (was configurable at 50). `GA_DASHBOARD_PORT_RANGE_SIZE` removed as a configurable env var.

---

## v0.3.2

### Security

- **Ed25519 admiral signing (TRN-136)** — Admiral mail signing moved from a shared HMAC secret to Ed25519 asymmetric keys. The private key never leaves the transport (persisted at `DATA_DIR/secrets/<crew_id>.admiral_secret`); each crew receives only the public key, mounted as a read-only, root-owned Podman secret it cannot modify even if compromised. The `X-Admiral-Sig` header and `verify-admiral-sig` exit-code contract (0/1/2) are unchanged. **Operator action required:** existing crews must be nuked and relaunched to pick up the new signing scheme — a plain restart does not migrate a crew. See [docs/auth.md](docs/auth.md).
- **Crew proxy no longer forwards transport credentials** — the crew UI/API proxy (`_handle_crew_ui_proxy` / `_handle_crew_api_proxy`) stopped forwarding the inbound `Authorization` and `X-Transport-Token` headers down to a crew's own gateway. Crew containers share the `ga-starboard` network with `ga-transport`, so a compromised crew that captured either header could previously replay it directly against the transport's own control-plane API. Neither header is used by the crew gateway — it authenticates purely via its own `mc_token_5476` session cookie — so nothing downstream depended on them.
- **`starlette` pinned to `>=1.0.1`** — closes CVE-2024-47874 and CVE-2026-48710.

### API

- **`GET /openapi.json` (TRN-129)** — new public, unauthenticated endpoint serving an OpenAPI 3.1.0 schema generated at startup from the live route table and MCP tool registry (HTTP routes with per-route auth requirements, plus MCP tools as synthetic `mcp-tools` paths). Intended as a self-documenting source of truth for client/tooling authors. A build-time script (`scripts/generate_openapi.py`) also writes the schema to disk for CI artefact capture. Reachable through Caddy's public port as well as directly on the transport.

### Fixes

- **Stale active-crew counts (TRN-132)** — `crews()` and the `GA_MAX_ACTIVE_CREWS` limit check now cross-reference the registry against actual Podman container state instead of trusting a potentially-stale `status: "running"` field. A crew stopped outside ghostship (`podman stop`, a VM reboot, an idle-monitor stop the registry missed) no longer inflates the active count or blocks legitimate launches — the registry self-heals the stale entry to `"stopped"` immediately, no transport restart needed.

### Captain templates

- **`independent-review`** — dispatches four concurrent independent reviewers (Wraith for docs, three Banshees for security/quality/test-coverage); `change_name` is optional — when provided, scopes the review to that change; when omitted, reviews the entire codebase. Consolidates findings by severity. (`independent-review-all` is merged into this template and deleted.)
- **`sdd`** — drives one or more named OpenSpec changes through the standard Spectre → Ghost → Banshee → Reaper lifecycle; `change_name` accepts a single name or a comma-separated list for parallel multi-change execution with automatic worktree isolation and merge reconciliation. (`sdd-parallel` is merged into this template and deleted.)
- **`<change?>`** token in `transport/captain.py` — optional change-name token: substitutes the provided name when `change_name` is given, or `"entire codebase"` when omitted. Raises if mixed with required `<change>` or `<changes>` in the same template body.
- **SDD reconciliation attempts conflict resolution before escalating (TRN-140)** — in parallel multi-change `sdd` execution, the reconciliation-phase Ghost task now reads each conflicting change's specs and tasks to understand intent, resolves merge conflicts by treating them as additive where possible, and re-runs the test suite, recording every decision in the Admiral mail. It previously escalated to the Admiral on the first conflict; now it only escalates if conflicts remain unresolved or tests still fail.
- **`transport://orders` is now a summary index (TRN-135)** — returns name + one-line description per standing-order template instead of every template's full body. Use the new `transport://orders/{name}` resource for a specific template's full text. New `GA_ORDERS_DIR` env var lets operators point at a directory of custom `.md` templates that merge with (and can override) the built-in `academy/orders/` set.

### Install

- **`--client-only`** flag — skips all container infrastructure (no Podman check, no image builds, no `compose up`) and wires up just the `ghostship` CLI and agent harness integrations. Designed for machines connecting to an already-running remote transport. Use with `--url` and optionally `--api-key`.
- **Transport source hash detection** — `install.sh` now hashes the transport source tree and embeds it as a label on the built image. On subsequent installs, if the version matches but the source has changed (mid-release commits), a clean rebuild is forced automatically.

### Testing

- Full-suite test bootstrap stabilized (TRN-144) — a shared httpx stub module (`tests/unit/_stubs.py`) fixes exception-identity mismatches that caused spurious `test_recovery.py` failures under the parallel test runner.
- `tests/integration/test_uninstall_auth_preservation.sh` is now actually wired into `scripts/run.sh`'s integration suite — it existed but was never executed.

---

## v0.3.0

### Breaking changes

**Re-run `./install.sh` to upgrade — in-place upgrade is not supported.**

- **`GA_PORTAL_PORT` renamed to `PORT`.** `install.sh` auto-migrates existing config files with a deprecation warning. Update your config to use `PORT` to silence it.
- **`ga-portal` (Caddy) is now mandatory.** The `GA_PORTAL_ENABLED` opt-in flag is removed — portal always runs. Any deployment previously running with `GA_PORTAL_ENABLED=false` must re-run `install.sh`.
- **`ga-net` replaced by two networks.** `ga-portside` (transport ↔ portal only) and `ga-starboard` (transport ↔ crews). Existing crew containers are migrated automatically on first startup after upgrade, but `install.sh` must be re-run to create the new networks.

### Dashboard (Caddy-backed, always on)

Crew dashboards are now proxied through `ga-portal` (Caddy) rather than per-port uvicorn threads in the transport. This is the only dashboard mode — the per-port proxy is removed.

- `launch(dashboard=True)` registers a per-crew Caddy server via the admin API and returns a `dashboard_url`. `nuke` removes it. Transport startup re-registers from `crews.json` (idempotent, no Caddy restarts).
- Every dashboard port is gated by a `gs_session` cookie. Unauthenticated requests go to `/dashboard/login`; `POST /dashboard/login` issues the cookie when `GA_API_KEY` is correct (open-access when `GA_API_KEY` is unset).
- The transport injects the `mc_token_5476` crew session cookie before forwarding to the crew gateway, resolving a 403 IP-mismatch that occurred when Caddy proxied directly.
- **TLS modes:** `off` (plain HTTP, default), `internal` (Caddy built-in CA), `tailscale` (browser-trusted `.ts.net` certs), `acme` (Let's Encrypt). Configured via `GA_PORTAL_TLS_MODE`. See [docs/caddy.md](docs/caddy.md).
- When `GA_API_KEY` is set, Caddy enforces `Authorization: Bearer` on `/mcp*` and `/files/*` at the edge before requests reach the transport.

### Network isolation

- `ga-portside` — `ga-portal` ↔ `ga-transport` only. Crew containers cannot reach `ga-portal`.
- `ga-starboard` — `ga-transport` ↔ crew containers. Crews cannot reach each other.
- `GA_TRANSPORT_SECRET` — a shared secret (auto-generated by `install.sh`, stored as Podman secret `ga-transport-secret`) gates every request from `ga-portal` to `ga-transport`. `TransportSecretMiddleware` rejects requests with a missing or wrong `X-Transport-Token` header.

### KiroCrew 0.5.0

Crew base image bumped from `0.4.0` to `0.5.0`. The `sandbox: "off"` override is patched into `config.local.json` at crew start — required for rootless Podman compatibility (KiroCrew 0.5.0's default sandbox mode fails with `EPERM` under rootless).

### Config cleanup ⚠️

Removed 6 env vars that are now hardcoded internally. No operator action needed — defaults are unchanged.

| Removed variable | Hardcoded to |
|:----------------|:-------------|
| `GA_FILE_TTL_SECS` | `300` |
| `GA_MEMORY_WAIT_SECS` | `60` |
| `KC_GATEWAY_TOKEN_TTL` | `"24h"` |
| `GA_ENFORCE_HTTPS_REDIRECT` | `False` (Caddy owns redirects) |
| `GA_CSP_ENFORCE` | `True` (always enforced) |
| `GA_PORTAL_ADMIN_URL` | `"http://ga-portal:2019"` |

### KIRO_API_KEY headless auth

Crews now support a `KIRO_API_KEY` env var for headless kiro-cli authentication, bypassing the interactive device flow. Useful for non-interactive deployments. See [docs/auth.md](docs/auth.md).

### Other improvements

- `crews()` response includes `uptime_secs` for running containers.
- Schedule monitor checks the crew gateway `/api/crons` as source of truth before firing jobs.
- Captain `stop` always updates the registry; the gateway cron call is best-effort.

## v0.2.4

### TRN-80 — Per-crew dashboard proxy
- `launch(dashboard=True)` allocates a dedicated port and returns a `dashboard_url` for the crew's browser UI (opt-in; `dashboard=False` by default)
- HTTP and WebSocket proxying to the KiroCrew SPA via per-port uvicorn daemon threads
- `POST/DELETE /crews/{id}/dashboard` REST API to attach or detach a dashboard port without nuke+relaunch
- Session cookie injection and CORS origin injection for browser authentication
- `GA_DASHBOARD_PORT_ENABLED`, `GA_DASHBOARD_PORT_RANGE_START`, `GA_DASHBOARD_PORT_RANGE_SIZE` environment variables
- Known limitation: dashboard ports are network-auth only (Tailscale/firewall); TRN-91/92 cover auth hardening

### TRN-89 — Timestamps on tool responses
- `dispatch` response includes `created_at`
- `pickup` (task-level) response includes `created_at`, `started_at`, `completed_at` (ISO 8601 UTC, `null` until reached)
- `captain status` response includes `last_checkin_at`
- Mail subjects (pickup, captain status) include `received_at` parsed from the message `Date` header

### TRN-90 — Bundle clone HEAD fix
- Fixed: `evac(bundle=True)` followed by `supply(bundle=True)` now correctly checks out the working tree when the bundle HEAD ref contains slashes (e.g. `release/0.2.4`)

### TRN-93 — Security hardening
- Admiral secret delivered via stdin instead of argv — no longer visible in `ps` or `/proc`
- `crews.json` stores an opaque sha256 identifier instead of the plaintext secret
- Container hardening: `no_new_privileges=True`, `cap_drop=[CAP_NET_RAW, CAP_SYS_ADMIN]`
- `KC_GATEWAY_TOKEN_TTL` validated on transport startup
- File-transfer audit logging

### TRN-94 — Broad mailbox skim
- `captain status` returns `agent_mail` covering all 8 mailboxes (ghost, spectre, banshee, wraith, reaper, raven, captain, admiral)
- Crew-level `pickup` (no `task_id`) returns `agent_subjects` covering all 8 mailboxes
- `pickup(agent="ghost", crew_id=...)` — new agent filter returns a single-inbox response with no task list
- `read_mail_subjects.py` updated to return `{subject, received_at}` dicts

### Fixes
- WebSocket pump: `asyncio.wait(FIRST_COMPLETED)` + cancel (replaces leaky `asyncio.gather`)
- httpx client pooling: one pooled `AsyncClient` per dashboard port (was re-created per request)
- DELETE dashboard atomicity: stop and release inside `_registry_lock`

---

## v0.2.3 and earlier

See git log for history prior to v0.2.4.
