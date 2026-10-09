# Tasks

## 1. Parsing and validation

- [x] 1.1 Parse `GA_AGENT_BACKENDS` in `Config.from_env()`: split, trim, lowercase, drop empty entries and duplicates, always include kiro, reject unknown names with `ConfigError` (D1, D2, D7).
- [x] 1.2 Validate `GA_CREW_ACP_BACKEND` against the enabled set in `Config.from_env()`, not `__post_init__`. The `ConfigError` names both settings and the `ghostship install` re-run (D3, D7).
- [x] 1.3 Reject `GA_INCLUDE_CLAUDE_AGENT` and `GA_INCLUDE_CODEX_AGENT` when present with a non-empty value, with a `ConfigError` naming `GA_AGENT_BACKENDS` (D5). Must land with 3.3.
- [x] 1.4 Log one inert-setting warning per setting, once, from the transport startup path in `server.py` (not from `Config`): the Anthropic settings while claude is disabled, the OpenAI settings while codex is disabled, and a stored `ga-claude-auth` or `ga-codex-auth` for a disabled backend. Never log values (D7).
- [x] 1.5 Remove `ga_include_claude_agent` and `ga_include_codex_agent` from `Config`, every read of them, and the stale comments in `transport/config.py` (around lines 195-197).
- [x] 1.6 Unit tests for each scenario in `specs/agent-backends/spec.md`, including a check that warnings don't contain the setting's value and are logged once per start.

## 2. Gating

- [x] 2.1 `POST /login/claude`, `POST /login/claude/code` and `POST /login/codex` check membership in the enabled set instead of `GA_CREW_ACP_BACKEND`, before parsing the body or looking up the pending flow. For a disabled backend, return 400 naming `GA_AGENT_BACKENDS` and the `ghostship install` re-run. `POST /login` (kiro) is unchanged (D6).
- [x] 2.2 Confirm `POST /logout/claude` and `POST /logout/codex` stay ungated, and add a test for logout with the backend disabled.
- [x] 2.3 Replace the launch guard's `GA_INCLUDE_CLAUDE_AGENT` check with a membership check covering claude and codex, and rename its error from `claude_backend_not_enabled` to `backend_not_enabled`. Defensive only; test by patching (D6).
- [x] 2.4 Update the error text, comments and docstrings in `transport/lifecycle.py` that name the retired flags (around lines 2024, 2494, 2772-2774, 2907, 2955).
- [x] 2.5 Tests: login is refused for a disabled backend (including before body validation on `/login/claude/code`), allowed for an enabled backend that isn't the default, and kiro is never refused. Flip `test_trn170…::test_returns_400_when_not_claude_backend` and `test_trn172…::test_returns_400_when_not_codex_backend`, which expect 400 when the backend is merely not the default. Update the tests that patch `cfg.ga_include_claude_agent` (`test_trn167`, `test_trn170`, `test_trn171`, `test_trn172`, `test_claude_login_fixes`).

## 3. Build and install

- [x] 3.1 Move the Claude and Codex install steps into `crews/spec-ops/toolchains/claude.sh` and `codex.sh`, keeping the current pinned versions (D4).
- [x] 3.2 Put the shell parser in `scripts/lib/agent_backends.sh`, sourced by `install.sh` and the tests (D1). It normalises the list, checks each name against `^[a-z][a-z0-9-]*$` and the toolchain script basenames, and checks `GA_CREW_ACP_BACKEND` against the set.
- [x] 3.2a `install.sh`: source the parser, pass `AGENT_TOOLCHAINS`, exit before building on a bad name, a default outside the set, or a retired flag. Remove the `GA_INCLUDE_*` defaults and build-arg lines. In `--client-only` mode, run only the retired-flag check (D8).
- [x] 3.3 Compose generation in `install.sh`: write `GA_AGENT_BACKENDS` into the transport environment, and remove the `GA_INCLUDE_*` entries. Must land with 1.3 (D5).
- [x] 3.4 Containerfile: one `ARG AGENT_TOOLCHAINS`, one `COPY toolchains/`, one loop with `set -e` that names a failing script, and `LABEL org.ghostship.toolchains=$AGENT_TOOLCHAINS`. No per-backend logic remains.
- [x] 3.4a `install.sh`: force a cache-less spec-ops build when the existing image's `org.ghostship.toolchains` label differs from the new `AGENT_TOOLCHAINS` (D4).
- [x] 3.5 Parity test, sourcing `scripts/lib/agent_backends.sh`: the shell and Python parsers agree on shared inputs (including messy case, duplicates and empty entries), and the transport's optional backends match the toolchain script basenames (D1).

## 4. Docs and config

- [x] 4.1 In `config/ghostship.conf.example` and `docs/configuration.md`, document `GA_AGENT_BACKENDS`, `GA_CREW_ACP_BACKEND`, `GA_CREW_ANTHROPIC_API_KEY`, `GA_CREW_ANTHROPIC_BASE_URL`, `GA_CREW_OPENAI_API_KEY` and `GA_CREW_OPENAI_BASE_URL`, each with its default, valid values and backend. Remove the `GA_INCLUDE_*` entries.
- [x] 4.2 Update `docs/auth.md` and `docs/architecture.md`: login is available for any enabled backend, and the prerequisites name `GA_AGENT_BACKENDS`.
- [x] 4.3 Migrate local `config/ghostship.conf` to `GA_AGENT_BACKENDS=claude` and re-run `ghostship install`. This file is gitignored.

## 5. Verification

- [x] 5.1 Build the image once with `AGENT_TOOLCHAINS=claude,codex` to prove both scripts work, and once with it empty to prove the kiro-only build.
- [x] 5.2 Rebuild with `GA_AGENT_BACKENDS=claude`. Confirm a Claude crew launches (`launch`, `dispatch`, `pickup`, then nuke the test crew).
- [x] 5.3 Confirm `POST /login/codex` returns 400 naming `GA_AGENT_BACKENDS` while codex is disabled.
- [x] 5.4 Run the full unit suite.

## 6. Ordering

- [x] 6.1 Archive `trn-202-claude-backend-fixes` before applying this change, since this change modifies its opt-in requirement.
