# Proposal

**Plane ticket:** TRN-233 (follow-up to the deferred `ghostship auth login <backend>` work)

## Why

Backend credentials currently have two owners. `install.sh` turns credential
variables in `ghostship.conf` into Podman secrets, deleting each secret on every
run and recreating it only when the conf still holds the value. The transport's
`/login*` flows separately store OAuth archives under `DATA_DIR`. The split
loses credentials without warning: `--wizard` rewrites the conf without its
secrets, and the next plain install then deletes the Podman secret. The wizard
and specs also point operators at `ghostship auth login anthropic|openai`, which
does not exist. The CLI ignores the backend argument and starts a Kiro device
flow instead. Rotating a credential means a reinstall and a transport restart,
because the transport reads every secret once at import time.

This change gives credentials a single owner: the `ghostship auth` command,
backed by the transport. The installer goes back to doing configuration only.

## What Changes

- **New `ghostship auth login <kiro|claude|codex>`**: an interactive command that
  offers that backend's credential methods and stores the result through the
  transport:
  - **kiro**: paste an API key; device code with Builder ID (social login); or
    device code with IAM Identity Center (enterprise; prompts for the start URL
    and region).
  - **claude**: authorisation code (browser OAuth with a pasted code); paste an
    API key; or paste a `claude setup-token` token.
  - **codex**: ChatGPT subscription (device-code sign-in, `codex login
    --device-auth`), or paste an OpenAI API key. This gives parity with Claude's
    subscription login.
- Every pasted secret is read from a hidden prompt or stdin, never from argv.
- **New `ghostship auth status`** and **`ghostship auth logout <backend>`**.
- **The CLI resolves the transport URL and bearer key the same way for every
  subcommand.** It uses flag, then env, then the installed transport's port
  and `DATA_DIR/ga-api-key`. This fixes the wizard's own Kiro login, which
  currently gets a 401 on keyed installs.
- **One active credential per backend.** Storing a credential replaces
  whatever that backend held before, so the API key > setup-token > OAuth
  precedence chain goes away.
- **The transport persists every backend credential as a 0600 file under
  `DATA_DIR`**, written atomically. Static secrets now use the same location as
  the OAuth archives already do.
- **The transport resolves credentials at each crew launch**, not at import, so
  rotation needs no reinstall or restart.
- **BREAKING:** `install.sh` no longer reads, creates or removes backend
  credential secrets (`ga-crew-anthropic-api-key`, `ga-claude-code-oauth-token`,
  `ga-crew-openai-api-key`, `ga-kiro-api-key`). It also stops honouring their
  conf variables and deprecated aliases. A credential variable left in
  `ghostship.conf` produces a warning naming the `ghostship auth login` command
  to run, and is otherwise ignored.
- **`KIRO_IDENTITY_PROVIDER` and `KIRO_REGION` stay in `ghostship.conf`** as
  non-secret configuration. When set, they make Identity Center the default
  Kiro device flow (for launch, and as prompt defaults in `ghostship auth login
  kiro`). Otherwise Builder ID is used.
- **Launch keeps starting interactive logins.** When the crew's backend has
  no stored credential, launch starts that backend's interactive flow and
  returns its `login_url` (and code):
  - kiro: Identity Center device code if configured, else Builder ID
  - claude: authorisation code
  - codex: ChatGPT device code
- **BREAKING, no migration:** after upgrading, every backend must be logged
  in again with `ghostship auth login <backend>`. Old Podman secrets, conf
  credential lines and existing login files are ignored.
- **BREAKING:** the Codex ChatGPT flow is rebuilt on `codex login
  --device-auth`, replacing the unproven `codex-acp login` and browser-redirect
  path. It is served at `POST /login/codex/chatgpt`.
- **The wizard** collects non-secret configuration only. After the transport is
  up, it offers to run `ghostship auth login <backend>` for each enabled backend.
- **Uninstall** keeps every backend credential file in `DATA_DIR`. Today only
  `ga-kiro-auth` survives. It also removes the now-unused credential Podman
  secrets.

## Capabilities

### New Capabilities

- `backend-credentials`: the transport-side credential store. It covers
  per-backend storage under `DATA_DIR`, one active credential per backend, the
  HTTP API the CLI uses to set, inspect and clear credentials, and per-launch
  resolution into crew containers.

### Modified Capabilities

- `trn-cli`: the auth subcommand group takes the form `ghostship auth <verb>
  [backend]`: `login <backend>` with interactive method selection,
  `logout <backend>` and `status`. URL and
  key resolution is shared across subcommands.
- `installation`: the installer stops creating credential secrets, warns about
  and ignores credential variables in the conf, and keeps collecting the Kiro
  Identity Center settings as config. The wizard hands off to `ghostship auth login` after
  start, and uninstall keeps all credential files.
- `secret-delivery-hardening`: the requirements that deliver backend
  credentials as Podman secrets are removed. The transport bearer key
  (`ga-api-key`) and `ga-transport-secret` are unchanged.
- `claude-setup-token-auth`: **retired.** The setup-token becomes a method of
  `ghostship auth login claude`, and its delivery and launch rules move into
  `backend-credentials`.
- `claude-auth`: the authorisation-code flow becomes one method of `ghostship
  auth login claude`. Its result is claude's single active credential, it may
  start while another credential is held, and its routes move under
  `/login/claude/oauth`.
- `codex-auth`: the old OAuth requirements are replaced by a ChatGPT
  device-code sign-in whose result is codex's single active credential.
- `crew-auth`: the Kiro method (API key, Builder ID, Identity Center) is
  explicit. Identity Center takes its settings from the request or the conf,
  and the state machine follows the credential store.
- `crew-login`: kiro's device login moves to `POST /login/kiro/builder-id`
  and `/identity-center`, and `POST /logout` moves to `POST /logout/kiro`. An
  existing credential no longer blocks a new flow.
- `config-file`: credential fields are removed from the documented conf
  fields, while the Kiro Identity Center fields remain. The auth docs centre on
  `ghostship auth`.
- `agent-backends`: inert-setting warnings cover stored credentials for
  disabled backends, not conf variables.
- `crew-acp-backend`: the Claude and Codex launch checks consult the
  credential store, and without a credential they start the backend's
  interactive login (authorisation code for claude, ChatGPT device code for
  codex).

## Impact

- **Code:** `ghostship` (CLI auth group); `scripts/install.sh` (secret blocks
  861-886, alias mapping, wizard, compose secret lines); `scripts/uninstall.sh`
  (`DATA_DIR` retention); `transport/server.py` and `transport/lifecycle.py`
  (module-level credential reads, launch gating, env injection, `/login*`
  routes, Codex ChatGPT login rebuild); `crews/spec-ops/toolchains/codex.sh`
  (possibly a pinned `@openai/codex` for device login); `transport/config.py` (credential fields); a
  new credential-store module. This builds on the `LoginFlow` classes from
  `trn-240-transport-refactor`, which must land first.
- **API (breaking):** the login surface becomes `POST
  /login/{backend}/{method}`, `GET /login/{backend}` and
  `POST /logout/{backend}`. Kiro's bare `/login` and `/logout` move under
  `/login/kiro` and `/logout/kiro`. Bare `/login` and `/logout` are left
  unassigned for a future browser login page.
- **Operators:** after upgrading, credentials are managed with `ghostship
  auth`. **BREAKING:** existing credentials (Podman secrets, conf lines,
  `ga-kiro-auth`, `ga-claude-auth`, `ga-codex-auth`) are not carried over.
  Every backend must be logged in again.
  Credential lines in `ghostship.conf` stop taking effect.
- **Tests:** `test_trn226_claude_oauth_token.py`, `test_trn172_codex_backend.py`,
  `test_ghostship_auth.py`, `test_server.py` (Kiro key), and every test that
  patches module-level credential globals need rewriting.
- **Docs:** `docs/auth.md`, `docs/configuration.md`, `README.md`,
  `config/ghostship.conf.example`.
- **Out of scope:** the transport bearer key (`GA_API_KEY`) lifecycle,
  Bedrock/Vertex authentication for Claude, and a browser login page (open
  `/login` in a browser and complete each backend's flow there instead of
  through API calls). These are noted as follow-ups.
