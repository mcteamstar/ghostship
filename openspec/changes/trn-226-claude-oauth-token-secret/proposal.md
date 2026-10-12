# Proposal

**Plane ticket:** TRN-226 (follow-up; supersedes the endpoint from archived change `2026-10-12-trn-226-claude-headless-auth`)
**Change:** `trn-226-claude-oauth-token-secret`

## Why

`POST /login/claude/setup-token` (added by TRN-226) cannot work as built. `claude setup-token` is an interactive browser approval that **prints** a long-lived token to stdout. It does not write `~/.claude/.credentials.json`. The endpoint offers no way to approve, throws stdout away, and polls for a file that never appears. It also runs blocking work (`container_exec`, `time.sleep`) on the async event loop, so one call hangs the whole transport until it is restarted (this happened on 0.7.0 on 2026-10-12). The OAuth refresh-staleness problem TRN-226 set out to solve is still open.

A setup-token is a static, long-lived credential the operator generates once on their own machine. That is the same shape as `KIRO_API_KEY`, `GA_CREW_ANTHROPIC_API_KEY` and `GA_CREW_OPENAI_API_KEY`, which already have a config, Podman-secret, crew-env delivery path. The token should use that path, not a login flow.

## What Changes

- New config var `CLAUDE_CODE_OAUTH_TOKEN` in `ghostship.conf`. The operator runs `claude setup-token` locally and pastes the result.
- `install.sh` delivers it as the Podman secret `ga-claude-code-oauth-token`, never as a plaintext compose env var. This follows the existing model-key pattern.
- The transport reads the secret at startup, registers it with the redaction filter, and injects it into Claude-backend crews as `CLAUDE_CODE_OAUTH_TOKEN`.
- Credential precedence for Claude-backend crews: `ANTHROPIC_API_KEY`, then `CLAUDE_CODE_OAUTH_TOKEN`, then `ga-claude-auth`. When a higher-precedence credential is set, `~/.claude/` is not injected, so a stale OAuth credential cannot shadow it.
- Fix: `lifecycle.py` read `KIRO_API_KEY`, `GA_CREW_ANTHROPIC_API_KEY` and `GA_CREW_OPENAI_API_KEY` from `cfg`, which is empty in production, so its "skip OAuth injection when an API key is set" checks never applied. Server and lifecycle now resolve all four credentials from their Podman secrets through `security.get_secret`, and the inert-setting warning checks the resolved values.
- **Renamed settings**: `GA_CREW_ANTHROPIC_API_KEY`, `GA_CREW_ANTHROPIC_BASE_URL`, `GA_CREW_OPENAI_API_KEY` and `GA_CREW_OPENAI_BASE_URL` become `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `OPENAI_API_KEY` and `OPENAI_BASE_URL`. These settings belong to Claude and Codex, so they use the names those CLIs read, as `KIRO_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` already do. `install.sh` still accepts the old names from `ghostship.conf`, with a warning. Podman secret names do not change.
- The launch auth gate accepts the token as a valid Claude credential, so no login flow is started.
- `CLAUDE_CODE_OAUTH_TOKEN` is added to the Claude backend's inert-setting warnings.
- **BREAKING**: `POST /login/claude/setup-token` and `_initiate_claude_setup_token` are removed. Callers get a 404. The interactive OAuth flow (`POST /login/claude` + `POST /login/claude/code`) is unchanged.
- `docs/auth.md`, `config/ghostship.conf.example` and the CHANGELOG are updated to describe the token path as the recommended headless option.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `claude-setup-token-auth`: the endpoint requirements are replaced by config-delivered token requirements (injection as `CLAUDE_CODE_OAUTH_TOKEN`, precedence, launch gate).
- `claude-auth`: the opt-in requirement no longer references the removed endpoint, and its docs requirement points at the token path. `~/.claude/` injection is skipped when the token is set.
- `secret-delivery-hardening`: adds a requirement that `CLAUDE_CODE_OAUTH_TOKEN` is delivered as a Podman secret; the model-key requirement uses the new names.
- `installation`: adds the standard-name and deprecated-alias requirements; existing requirements use the new names.
- `agent-backends`, `codex-auth`, `crew-acp-backend`, `crew-auth`: requirement text uses the new setting names (no behaviour change).

## Impact

- `scripts/install.sh`: config default, Podman secret block, compose `secrets:` wiring.
- `transport/config.py`: new field, `_BACKEND_SETTINGS["claude"]`.
- `transport/server.py`: secret read and redaction, crew env injection, launch gate, removal of the route and handler.
- `transport/lifecycle.py`: removal of `_initiate_claude_setup_token`, skip `~/.claude/` injection when the token is set.
- Tests covering the removed endpoint are deleted or rewritten. New tests cover secret read, injection, precedence and the gate.
- Docs: `docs/auth.md`, `config/ghostship.conf.example`, `CHANGELOG.md`.
- Operators who relied on `POST /login/claude/setup-token` (it never succeeded, so likely none) must switch to the config var.
