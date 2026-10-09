# Proposal

## Why

Switching the crew backend from kiro to Claude Code (`GA_CREW_ACP_BACKEND=claude`) does not work end to end yet. The first attempt exposed four problems:

- The spec-ops image pins `@anthropic-ai/claude-code@0.2.93`, which has no `claude auth login` subcommand. Login falls through to the interactive session and never prints a URL.
- The login URL extractor captures terminal control codes (OSC-8 hyperlinks, BEL, colour codes) into the returned URL, so the URL cannot be opened as returned.
- Claude's OAuth flow is an authorisation-code flow. The browser shows the user a code that must be pasted back into the CLI. The transport has no endpoint for that step, so a login can never complete.
- The completion check treats any non-empty file under `~/.claude/` as "logged in". On the first attempt the match was a config backup, so the transport reported success and saved an archive with no credentials. The user never approved anything.

Fixing these makes the Claude backend usable with a Claude Pro or Max subscription, as `claude-auth` intends.

## What Changes

- **Pin a Claude Code CLI version that provides `claude auth login`.** Move the spec-ops image pin from `@anthropic-ai/claude-code@0.2.93` to a version verified to provide the `auth login` subcommand. Confirm the ACP adaptor (`@agentclientprotocol/claude-agent-acp@0.79.0`) works with that CLI before the pin is accepted.
- **Strip terminal control sequences before URL extraction.** The shared PTY login helper removes ANSI CSI and OSC sequences from the output before the URL and code patterns run. Kiro's login path uses the same helper and benefits without any change to its behaviour.
- **Add a paste-back endpoint for the Claude authorisation code.** A new `POST /login/claude/code` accepts the code the user copies from the browser and writes it to the pending login's PTY. This is the one step with no kiro equivalent. Kiro's device flow has the CLI poll for its own token.
- **Tighten Claude login completion to the real credential.** Completion is detected only when the CLI's credential file exists and is non-empty. It is no longer any non-empty file under `~/.claude/`. The archive written to `ga-claude-auth` must contain that credential file, and the transport refuses to save an archive that does not.
- **Stop reporting false successes.** The audit log entry `outcome=success` is written only after the credential check passes.
- **BREAKING (operator-visible):** `POST /login/claude` now returns a flow that needs `POST /login/claude/code` before it completes. Existing clients that only poll `GET /login/claude` will see the flow sit pending until the code is submitted.

## Capabilities

### New Capabilities

None. The fixes sit inside the existing Claude login capability.

### Modified Capabilities

- `claude-auth`: login now requires a paste-back step; URL extraction strips terminal control sequences; completion is detected from the CLI's credential file rather than any file under `~/.claude/`; the audit log records success only on a verified credential.

## Impact

- **Image build**: `crews/spec-ops/Containerfile` (Claude Code pin; temporary `make`/`g++` install for the native build of `better-sqlite3`, to be removed if the new CLI no longer needs it). `docs/configuration.md` version reference.
- **Transport**: `transport/lifecycle.py` (`_run_pty_login_flow` escape stripping; `_initiate_claude_login` and `_poll_claude_login_container` completion check), `transport/server.py` (new `POST /login/claude/code` route; audit logging on completion).
- **Tests**: `tests/unit/test_trn170_claude_subscription_oauth.py` and `test_trn167_claude_backend.py` need updating for the new completion check and paste-back. The kiro login tests must keep passing after the shared helper change.
- **Operators**: a Claude login is now a two-step action (start, then submit the code). `docs/auth.md` needs the new step.
- **Not in scope**: API-key authentication, the Codex backend, and the kiro login flow's behaviour. Kiro is touched only through the shared URL helper.
