# Tasks

## 1. Spike: confirm the CLI behaviour on 2.1.293

- [x] 1.1 Credential file: `~/.claude/.credentials.json`, written about one second after the code is submitted. Confirmed in a real login on 2.1.293 (recorded in D4).
- [x] 1.2 Code input: the CLI prints `Paste code here if prompted > ` and completes the exchange when the pasted `<code>#<state>` value and a newline are written to the PTY (recorded in D3).
- [x] 1.3 Escape sequences: the PTY capture on 2.1.293 contains the URL as plain text with `\r\n` and no control sequences. The OSC-8 and colour codes seen through the transport must come from the transport's terminal settings (TERM or width). Stripping stays in place (task 2.1) because the transport's stream does contain them. Test coverage uses the transport's captured bytes as the fixture.

## 2. Shared PTY helper

- [x] 2.1 Add control-sequence stripping to `_run_pty_login_flow` (D2), applied to the accumulated text before prompt and URL patterns run.
- [x] 2.2 Unit test: a URL wrapped in OSC-8 and colour codes is returned clean, including when the sequence is split across two reads.
- [x] 2.3 Unit test: the kiro login URL extraction returns the same value before and after the change, for the existing kiro fixture output.

## 3. Claude login flow

- [x] 3.1 Keep the PTY socket open after the URL is returned for the Claude flow, and store it in `_claude_login_pending` (D3). The drain thread must not consume the socket during a pending code exchange.
- [x] 3.2 Add `POST /login/claude/code` (400 on a malformed body, 404 with no pending flow, 202 once the code is written). Do not log or echo the code.
- [x] 3.3 Replace the completion check in `_poll_claude_login_container` with the credential-file check (D4). Only the credential file and the archive are written on success.
- [x] 3.4 Add a deadline on the pending flow after the code is submitted. On expiry, nuke the container and clear the pending state.
- [x] 3.5 Write the audit log entry only after `ga-claude-auth` is saved, with `outcome=success` or `outcome=failure` (D5).
- [x] 3.6 Unit tests covering each scenario in `specs/claude-auth/spec.md`, including the config-backup-only case that caused the false completion.

## 4. Image pin and verification

- [x] 4.1 Update `crews/spec-ops/Containerfile` to `@anthropic-ai/claude-code@2.1.293` and `docs/configuration.md` to match. Remove the temporary `make`/`g++` install if the new CLI's build does not need it, and confirm the image still builds.
- [x] 4.2 Run one Claude-backend crew task on the rebuilt image, to confirm the ACP adaptor works with 2.1.293. Record the result before the pin is accepted.
- [x] 4.3 Run the full unit suite (`tests/run.sh --unit`), including the kiro login tests. Result: 1175 passed, 0 failed.

## 5. Docs

- [x] 5.1 Update `docs/auth.md` with the two-step Claude login (start, then submit the code), and the completion behaviour.
- [x] 5.2 Update the `GA_INCLUDE_CLAUDE_AGENT` row in `docs/configuration.md` if the pin text differs from 4.1.

## 6. Follow-up issues from the first working run

- [x] 6.1 Haiku model override: `KC_MODEL_OVERRIDE=claude-haiku-5-5` set in local config. Verified with a fresh crew: `HAIKU_SMOKE_OK` with no fallback warning.
- [x] 6.2 Approval deadline: a login never approved expires after 900s (410, container removed, audit failure). Spec scenario added.
- [x] 6.3 Opt-in: Claude requires `GA_INCLUDE_CLAUDE_AGENT=true` plus `GA_CREW_ACP_BACKEND=claude`. `POST /login/claude` returns 400 and `launch` returns `claude_backend_not_enabled` otherwise. Kiro remains the default. Documented in `config/ghostship.conf.example`.
- [x] 6.4 Stale dashboard relay tests (`_WsBytesMessage`, removed in 0.5.0) rewritten to the current str/bytes contract. Note: they mirror the relay logic, not the nested closure.
- [x] 6.5 Launch instructions now include the paste-back step.

