# Design

## Context

See proposal.md (Why). Today's credential handling has four separate parts:

- **Static secrets.** `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`,
  `OPENAI_API_KEY` and `KIRO_API_KEY` go from `ghostship.conf` to install.sh
  (rm, then conditional create, at install.sh:861-886), into Podman secrets,
  then `/run/secrets` in `ga-transport`. `_security.get_secret` reads them at
  import time in three places after TRN-242: `transport/tools.py` (~270-280,
  module-level globals used in `launch()`), `transport/login.py` (~112-116,
  used in `_finish_crew_setup` injection), and `transport/server.py` (~458-465,
  ~643, remnants not yet cleaned up).
- **Interactive login state.** The PTY flows write `DATA_DIR/ga-kiro-auth`
  (base64 SQLite rows), `ga-claude-auth` (tar of `~/.claude`) and
  `ga-codex-auth` (tar of `~/.codex`). These writes are 0600 but not atomic
  (truncate in place).
- **Precedence.** Precedence is open-coded in launch gating (`tools.py`
  ~586-650 after TRN-242), env injection, and `_finish_crew_setup`
  (lifecycle.py).
- **The CLI.** It only knows `POST/GET /login/kiro` and `POST /logout/kiro` (kiro). It
  takes the URL and key from flags or `GHOSTSHIP_URL`, and nothing else.

`trn-240-transport-refactor` introduces a `LoginFlow` base class with Kiro,
Claude and Codex subclasses in `transport/login.py`. `trn-242-server-modularisation`
extracted MCP tools to `transport/tools.py` and login HTTP handlers to
`transport/login.py`. This change builds on both and lands after them.

## Goals / Non-Goals

**Goals:**
- One module owns backend credentials in the transport: storage, status,
  replacement, clearing and per-launch resolution. No module-level credential
  globals remain.
- The installer has no code path that can create, delete or mount a backend
  credential.
- The CLI works against a local keyed install with no flags.

**Non-Goals:**
- Changing the transport bearer key (`ga-api-key`) or `ga-transport-secret`
  lifecycle. Install still writes `ga-api-key` from `--api-key` or the conf.
- Bedrock or Vertex for Claude. Codex Enterprise access tokens
  (`codex login --with-access-token`).
- Encrypting credentials at rest beyond 0600 file permissions on the data
  volume, which is the same protection the login archives have today.

## Decisions

### 1. Credential store: one JSON envelope per backend under `DATA_DIR/credentials/`

Each backend gets `DATA_DIR/credentials/<backend>.json` (mode 0600, directory
0700) holding:

```json
{"backend": "claude", "method": "setup-token", "stored_at": "<iso8601>",
 "provider": null, "payload": "<base64>"}
```

- The payload is the raw secret for static methods, the existing base64 rows
  for kiro device methods, and the tar bytes for Claude `oauth`.
- `provider` is `{"start_url", "region"}` for `identity-center`.
- Writes go to a temp file in the same directory, then `fsync`, then
  `os.replace`, which makes them atomic. TRN-240's `_write_secret_file`
  truncates in place, so the store does not use it.
- A `CredentialStore` class in `transport/credentials.py` exposes `get(backend)`,
  `put(backend, method, payload, provider=None)`, `delete(backend)` and
  `status()`. Every value it reads is passed through
  `_security.register_secret` so redaction still applies.

*Alternatives:*
- **Keep separate files per method, as today.** That keeps precedence logic
  alive and makes "one active credential" a cleanup rule rather than a
  structural fact.
- **Use Podman secrets written by the CLI.** The CLI would need host Podman
  access for every auth operation, the transport would still need a restart to
  see new secrets, and it would contradict the directive that auth goes
  through the transport.

### 2. No migration

This is a clean break. The transport never reads the old Podman secrets or
the legacy `ga-kiro-auth`, `ga-claude-auth` and `ga-codex-auth` files.
Operators log in again after upgrading. This avoids carrying import code (and
a host-side Podman secret reader) for a one-time transition.

### 3. HTTP surface

Every route has the form `/login/{backend}/{method}` or `/logout/{backend}`.
The method segment is the same word the CLI's `--method` and the status
response use.

| Route | Purpose |
|---|---|
| `GET /login/{backend}` | that backend's status (method, stored time, pending flow; no values), polled while a flow runs |
| `POST /login/kiro/api-key` | store a pasted key `{secret}` |
| `POST /login/kiro/builder-id` | start a Builder ID device flow |
| `POST /login/kiro/identity-center` | start an Identity Center device flow `{start_url?, region?}` (defaults from conf) |
| `POST /login/claude/oauth` | start the authorisation-code flow |
| `POST /login/claude/oauth/code` | submit the code `{code}` |
| `POST /login/claude/api-key`, `POST /login/claude/setup-token` | store a pasted secret `{secret}` |
| `POST /login/codex/chatgpt` | start the ChatGPT device flow (design §7) |
| `POST /login/codex/api-key` | store a pasted key `{secret}` |
| `POST /logout/{kiro,claude,codex}` | clear, cancel pending flow, wipe running crews; idempotent |

These are breaking moves, with no aliases:

- `POST /login` and `GET /login` (kiro) move to `/login/kiro/...`.
- `POST /logout` moves to `/logout/kiro`.
- `POST /login/claude` and `POST /login/claude/code` move under
  `/login/claude/oauth`.
- `POST /login/codex` moves to `/login/codex/chatgpt`.
- Bare `/login` and `/logout` are left unassigned (404), reserved for the
  future browser login page. `ghostship auth status` calls
  `GET /login/{backend}` once per backend.

All of these routes go in `BearerAuthMiddleware`'s authenticated `routes`.
Caddy already passes `/login*` and `/logout*` through, so it needs no change.
The rate-limit rule, which today matches only the exact `/login` path, is
widened to `POST /login/*`.

On completion, the interactive flows call `CredentialStore.put`, which
replaces the backend's credential. Starting a flow no longer returns 409 when
a credential exists. The CLI does the "are you sure" check before replacing
anything.

### 4. Per-launch resolution replaces precedence chains

Launch gating, env injection and `_finish_crew_setup` each call
`store.get(backend)` once per launch and switch on `method`:

| Method | Delivery |
|---|---|
| kiro `api-key` | `KIRO_API_KEY` env |
| kiro `builder-id`/`identity-center` | inject SQLite rows (existing `_inject_auth`) |
| claude `api-key` | `ANTHROPIC_API_KEY` env |
| claude `setup-token` | `CLAUDE_CODE_OAUTH_TOKEN` env |
| claude `oauth` | `~/.claude` archive (existing `_inject_claude_auth`) |
| codex `api-key` | `OPENAI_API_KEY` env |
| codex `chatgpt` | `~/.codex/auth.json` (archive put, like Claude) |

`ANTHROPIC_BASE_URL` and `OPENAI_BASE_URL` stay as configuration in the
compose environment.

When there's no credential, launch starts the backend's interactive flow
through the same `LoginFlow` the CLI uses, and returns `not_authenticated`
with `login_url`, `code` and instructions, as it does today:

- kiro: `identity-center` when `KIRO_IDENTITY_PROVIDER`/`KIRO_REGION`
  are configured, else `builder-id`
- claude: `oauth`
- codex: `chatgpt`

A flow that's already pending is reused rather than duplicated. An API-key
method never needs a flow. Completion stores into the credential store, so
the next launch succeeds.

### 5. Install is config-only

- The secret blocks for the four backend credentials (install.sh:858-886) are
  deleted, along with their compose lines (1062-1065, 1091-1094).
- The four credential variables and their two deprecated aliases stay on the
  reset list. If the conf sets any of them, install prints the warning and
  unsets them.
- `KIRO_IDENTITY_PROVIDER`, `KIRO_REGION`, `KIRO_LICENSE` and the
  `--identity-provider`/`--region` flags are unchanged. They are config, passed
  to the transport as today, and used as the Identity Center defaults.
- After the transport is ready, the wizard runs
  `ghostship auth login <backend>` for each enabled backend that the status
  call reports as unconfigured.
- Uninstall keeps `credentials/` and deletes it with `--purge-auth`. The old
  login files are not exempt, so they are removed. Uninstall also removes the
  four obsolete credential Podman secrets by name.

### 6. CLI shape and discovery

- `ghostship auth <verb> [backend]`, where the verb is `login`, `logout`,
  or `status`.
- Methods are picked from a numbered menu, or with `--method`. Secrets are
  read with `getpass` on a terminal, or from `sys.stdin.read()` otherwise.
- **URL discovery** reuses `ghostship status`'s Podman inspect of the
  installed containers to find the host port.
- **Key discovery** reads `ga-api-key` from the host directory mounted at
  `/data` in `ga-transport`, found with the same Podman inspect (the mount's
  `Source`). That avoids re-deriving the data directory or guessing which conf
  file the install used.
- Pasted secrets and codes are only sent over `https://` or to a loopback
  host unless `--insecure` is passed.
- Either discovery step falling back is silent. The explicit order is in the
  trn-cli spec.

### 7. Codex ChatGPT sign-in rebuilt on `codex login --device-auth`

ChatGPT sign-in is kept so Codex has a subscription option, matching
Claude's. The current implementation (`codex-acp login`, a browser redirect to
`localhost:1455`) can't complete from a container and its URL patterns were
never matched against real output, so it is replaced rather than ported.

- **Command:** OpenAI documents `codex login --device-auth` (beta) as the
  headless route. It prints a link and a one-time code, and writes
  `~/.codex/auth.json` on completion. `CodexLoginFlow` runs it in the
  `ga-codex-login-*` container with `CODEX_HOME` pointing at a known path and
  file-based credential storage (`cli_auth_credentials_store = "file"`), then
  polls for `auth.json`.
- **Binary:** the crew image installs only `@agentclientprotocol/codex-acp`,
  which bundles its own Codex binary. Task 3.4 first checks whether that
  binary exposes `login --device-auth`. If not, `toolchains/codex.sh` also
  installs a pinned `@openai/codex` CLI, used only by the login container.
- **Account prerequisite:** device code login has to be enabled in the ChatGPT
  account's security settings (personal) or by a workspace admin. When Codex
  reports it unavailable, the error says so, and the CLI prints the note up
  front.
- **URL and code extraction** is written against captured real output, and
  the test fixtures come from that capture rather than guessed patterns.

## Risks / Trade-offs

- [Codex device code login is beta, and is off unless the account or
  workspace enables it] → Clear error and up-front CLI note. API key remains
  the other codex method.
- [Codex refreshes ChatGPT tokens inside each crew, so the stored
  `auth.json` goes stale and refresh-token rotation in one crew may log out
  others, much like the Claude OAuth staleness already seen] → Accepted for
  parity. A refresh in a running crew isn't written back. Re-run `ghostship
  auth login codex` when crews start failing auth. Write-back is a follow-up.

- [Credentials sit on the data volume rather than in Podman's secret store] →
  0600 file in a 0700 directory, on the same volume and with the same
  protection the login archives already have. The Podman file driver stores
  secrets unencrypted on disk too, so the at-rest protection is the same.
- [Upgrading drops every stored credential, so crews fail to launch until the
  operator logs in again] → Intentional. The first launch on each backend
  starts its login and returns the URL, the wizard offers login for each
  unconfigured backend, and the release notes call it out.
- [Removing module-level globals breaks many tests that patch them (see
  tasks)] → Tests switch to an injected or temp-dir `CredentialStore`, which
  also removes the duplicated server.py and lifecycle.py copies.

## Migration Plan

1. Land `trn-240-transport-refactor`.
2. Ship the transport, CLI and installer changes together in one release.
3. Operators upgrading run `ghostship install`, then `ghostship auth login
   <backend>` for each enabled backend. Nothing is carried over.

**Rollback:** the previous release doesn't read `credentials/`, so operators
re-enter credentials the old way (conf plus reinstall, or `/login*`).

## Open Questions

- **Follow-up (not this change):** a browser login page at `/login` that
  walks through each backend's flow, so operators open one URL instead of
  driving API calls. The per-backend, per-method routes here are the API that
  page would call.

- MCP clients that get a Claude `login_url` from `launch` have no MCP tool
  to submit the code; they need `POST /login/claude/oauth/code`. That gap
  exists today. An MCP tool for it is a follow-up.
- Whether `ghostship auth status` should also appear in `ghostship status`
  output. This is cosmetic and can be decided during implementation.
