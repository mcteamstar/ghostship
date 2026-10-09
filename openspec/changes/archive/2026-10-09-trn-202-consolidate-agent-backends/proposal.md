# Proposal

## Why

Agent backend configuration is spread across independent variables. The backend switch (`GA_CREW_ACP_BACKEND`) is the only exclusive choice. The install-time image flags (`GA_INCLUDE_CLAUDE_AGENT`, `GA_INCLUDE_CODEX_AGENT`) can disagree with it, credentials for disabled backends are silently ignored, and Claude and Codex login only work when their backend is the default. Operators who run Claude or Codex, which is most people, are treated as add-ons to kiro. Consolidating the choice into one enabled set is the first step toward treating the three backends equally, and a prerequisite for later per-session selection.

## What Changes

- **New `GA_AGENT_BACKENDS`**: a comma-separated list of enabled agent backends, for example `claude,codex`. Valid names are `kiro`, `claude` and `codex`. Case, whitespace, empty entries and duplicates are normalised.
- **Kiro is always enabled.** KiroCrew bundles kiro in every image, so the enabled set always contains kiro. Listing it is harmless and omitting it changes nothing. Unset means kiro only.
- **The image build derives from the set.** `install.sh` passes one build arg, `AGENT_TOOLCHAINS`, listing the enabled optional backends. The spec-ops image runs one toolchain script per listed backend from `crews/spec-ops/toolchains/`. A new backend's toolchain is a new script, with no change to the Containerfile or `install.sh`.
- **The transport receives the set.** `install.sh` writes `GA_AGENT_BACKENDS` into the transport environment, from the same value used for the build.
- **The default backend stays in `GA_CREW_ACP_BACKEND`.** It must be an enabled backend, and defaults to `kiro`.
- **Login follows the set, not the default.** `POST /login/claude`, `POST /login/claude/code` and `POST /login/codex` work for any enabled backend, including one that isn't the default. For a disabled backend they return 400 naming `GA_AGENT_BACKENDS`. Logout stays available for every backend, so stored credentials can always be removed.
- **Startup validation.** Unknown backend names, and a default backend outside the set, raise `ConfigError` at startup. Messages name the settings and the `ghostship install` re-run.
- **Inert settings warn.** Anthropic or OpenAI settings, and stored `ga-claude-auth` or `ga-codex-auth` credentials, for a disabled backend are logged as inert at startup. Warnings name the setting, never its value.
- **BREAKING:** `GA_INCLUDE_CLAUDE_AGENT` and `GA_INCLUDE_CODEX_AGENT` are removed. If either is present with a non-empty value, the transport and `install.sh` fail with a message naming `GA_AGENT_BACKENDS`. The dev phase has no compatibility obligation, so there are no aliases. Recorded in `CHANGELOG.md`.
- **Out of scope:** per-session or per-crew backend selection, the `AgentBackend` interface refactor, consolidating the login handlers and pending-login state, an approval deadline for kiro and Codex logins, renaming routes, and renaming `KC_*` or `GA_CREW_AGENT`.

## Capabilities

### New Capabilities

- `agent-backends`: parsing and validation of `GA_AGENT_BACKENDS`, the always-on kiro backend, the default-backend rule, inert-setting warnings, login availability per enabled backend, and rejection of the retired flags.

### Modified Capabilities

- `installation`: the Claude and Codex toolchains come from per-backend scripts driven by `AGENT_TOOLCHAINS`. The transport environment carries `GA_AGENT_BACKENDS`. The two `GA_INCLUDE_*` requirements are removed.
- `crew-acp-backend`: `GA_CREW_ACP_BACKEND` must be an enabled backend. The Codex image requirement is restated in terms of the set.
- `claude-auth`: the Claude opt-in requirement is restated in terms of the set, and Claude login no longer requires claude to be the default.
- `codex-auth`: the Codex login container requirement is restated in terms of the set, and Codex login no longer requires codex to be the default.

## Impact

- **Config**: `transport/config.py` (parse and validate the set; reject the retired flags; remove `ga_include_claude_agent` and `ga_include_codex_agent`).
- **Transport**: `transport/server.py` (login gating by membership; launch guard renamed to `backend_not_enabled`; inert-setting warnings at startup), `transport/lifecycle.py` (error messages that name the retired flags).
- **Install**: `scripts/install.sh` (derive and validate `AGENT_TOOLCHAINS`; write `GA_AGENT_BACKENDS` into compose; remove its own `GA_INCLUDE_*` defaults, build args and compose entries; reject the retired flags).
- **Image**: `crews/spec-ops/Containerfile` gains one `ARG`, one `COPY toolchains/` and one loop. The Claude and Codex install steps move to `crews/spec-ops/toolchains/claude.sh` and `codex.sh`.
- **Tests**: new tests for `agent-backends`; updates to `test_trn167`, `test_trn170`, `test_trn171`, `test_trn172` and `test_claude_login_fixes`, which patch `cfg.ga_include_claude_agent` today.
- **Docs**: `config/ghostship.conf.example`, `docs/configuration.md`, `docs/auth.md`, `docs/architecture.md`.
- **Operators**: any config that sets `GA_INCLUDE_*` must move to `GA_AGENT_BACKENDS` and re-run `ghostship install`. This includes local `config/ghostship.conf` on this machine.
- **Ordering**: `trn-202-claude-backend-fixes` must be archived first, since this change modifies its opt-in requirement.
