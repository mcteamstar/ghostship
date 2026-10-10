# Design

## Context

The Claude login reuses the kiro login shape: an ephemeral `ga-claude-login-*` container, `claude auth login` run over a PTY via `_run_pty_login_flow`, and a `GET` poll that saves the credential and removes the container. Three things differ.

1. Kiro uses a device flow. The CLI polls for its own token, so the transport only reads state. Claude uses an authorisation-code flow. The browser shows a code that the user must return to the CLI.
2. The CLI output wraps the URL in terminal control sequences. The shared URL regex (`https?://\S+`) captures them.
3. The completion check was written against a guessed filename. It matched a config backup.

## Goals / Non-Goals

**Goals**
- A Claude login completes only when the CLI has actually stored a credential, and the returned URL is clean.
- The paste-back step uses the same ephemeral container and PTY as the start step.
- Changes to the shared helper leave kiro behaviour unchanged.

**Non-Goals**
- Changing the kiro device flow or its completion check.
- Changing API-key authentication.
- Automating the browser approval.

## Decisions

### D1. Pin a CLI version that has `claude auth login`

Move the spec-ops pin from 0.2.93 to 2.1.293. Version 2.1.293 was checked in a throwaway container: `claude auth` lists `login`, `logout` and `status`. 0.2.93 falls through to the interactive session.

The ACP adaptor `@agentclientprotocol/claude-agent-acp@0.79.0` declares `@anthropic-ai/claude-agent-sdk@0.3.274` as a dependency. The pin change is not accepted until a crew task runs on the new CLI (task 4.2).

### D2. Shared control-sequence stripping in `_run_pty_login_flow`

Strip CSI (`ESC [ … final`), OSC (`ESC ] … BEL` or `ESC \`), and bare BEL from the decoded text before any pattern runs. Doing it in the shared helper means kiro gets the same protection. Kiro's current output contains no such sequences, so its behaviour does not change.

Stripping is applied to the accumulated text, not per chunk. A sequence can be split across two `recv` calls, and per-chunk stripping would miss it.

### D3. Paste-back writes to the PTY the flow already owns

`_run_pty_login_flow` hands the socket to a drain thread once a URL is found. The drain thread keeps reading until EOF. That reading is required: without it the CLI can block on a full PTY output buffer. Writing to the same socket does not conflict with the drain, so the drain stays.

Design: `_initiate_claude_login` stores the socket and login URL in `_claude_login_pending` and marks the flow `awaiting_code`. `POST /login/claude/code` writes the code plus a newline with `sendall` and marks the flow `code_submitted`. The socket is closed by the drain thread when the CLI exits, or when the flow is cleaned up.

Spike 1.2 result (2.1.293): after printing the authorisation URL, the CLI prints `Paste code here if prompted > ` and waits on the PTY for input. In a real login, writing the pasted value plus a newline completed the exchange. The browser shows the value as `<code>#<state>`, and it was accepted as pasted, so the transport should pass it through unchanged.

### D4. Completion is the CLI's credential file, not any file

The poll checks for the credential file the CLI writes after a successful token exchange, and requires it to be non-empty. The archive written to `ga-claude-auth` holds that file. The transport also refuses to write an archive that lacks it.

Spike 1.1 result (2.1.293): the CLI builds its credential path as `join(configDir, ".credentials.json")`, so the credential file is `~/.claude/.credentials.json`. The same bundle also names `.device-keys.json`, and the `.claude.json.backup` file that caused the false completion. Completion should check `.credentials.json` only.

Observed in a real login (2.1.293, throwaway container): `~/.claude/` held only `backups/` before the exchange. About one second after the pasted code was written to the PTY, `.credentials.json` appeared (516 bytes) with a single top-level key, `claudeAiOauth`. The `backups/` directory holds the `.claude.json.backup.*` file that the old check matched, so `backups/` must not count as completion.

Related fix: the existing `claude_code_pattern` (`[?&]code=…`) matches the `code=true` parameter in the authorisation URL, so the `code` value in the `POST /login/claude` response is wrong. The response should not return a `code` for this flow.

### D5. Audit log moves to the write

`action=login outcome=success` is written after `ga-claude-auth` is saved, not when `GET` returns. Failures are logged with `outcome=failure` and the reason, so a stalled or rejected code is visible.

## Risks / Trade-offs

- **The code may be consumed by the drain thread.** D3 changes when the drain thread stops. A regression here would make paste-back silently fail. Mitigated by a unit test that asserts the socket is writable after the URL is returned.
- **Credential filename unknown until spike.** The whole completion fix depends on it. Mitigated by task 1.1 running before any code change.
- **Pin change may break the ACP adaptor.** Mitigated by task 4.2, which runs a real crew task before the pin is accepted.
- **Timeout after the code is pasted.** If the CLI never finishes the exchange, the flow stays pending. `GET` needs a deadline, after which the container is nuked and the pending state cleared.

## Migration Plan

1. Land the spike results in `design.md` (D4 filename, D3 input format).
2. Land the shared-helper stripping with tests that cover kiro unchanged.
3. Land the paste-back endpoint and completion check.
4. Rebuild the spec-ops image and run one Claude crew task. Only then update `docs/auth.md`.

Rollback: revert the Containerfile pin and the transport change. The ephemeral login containers are removed by the existing startup reconcile (see `claude-auth` orphan requirement), so no data migration is needed. Delete `ga-claude-auth` if it was written by the faulty completion check.
