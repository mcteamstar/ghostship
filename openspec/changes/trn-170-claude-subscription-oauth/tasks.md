## 1. PTY Login Flow — Claude OAuth

- [ ] 1.1 Add `_start_claude_login_container` to `lifecycle.py`: create and start an ephemeral `ga-claude-login-<token>` container from `localhost/spec-ops:latest`; fail with a clear error if the image is not found or does not have `claude` installed
- [ ] 1.2 Confirm the exact `claude auth login` command and PTY output format: run `claude auth login` in a test container and record the verification URL pattern and any interactive prompts it produces; document the URL regex used for extraction in a comment
- [ ] 1.3 Add `_initiate_claude_login` to `lifecycle.py`, mirroring `_initiate_login`: exec `claude auth login` (or equivalent device-code flag) via `container_exec_pty_stdin`, run the 45-second PTY read loop with `select()`, answer any interactive prompts, extract the verification URL, drain PTY in background, store pending state in `_claude_login_pending`
- [ ] 1.4 Add `_nuke_claude_login_container` to `lifecycle.py` (mirrors `_nuke_login_container`)
- [ ] 1.5 On login completion (detected by polling `~/.claude/` inside the login container for a non-empty credential file), tar `~/.claude/` and write it to `DATA_DIR/ga-claude-auth` (mode 0600), then nuke the login container

## 2. Transport Endpoints

- [ ] 2.1 Add `POST /login/claude` to `server.py`: enforces the three-state machine (409 if already authenticated or flow in progress), calls `_initiate_claude_login`, returns `{"login_url", "code"}`
- [ ] 2.2 Add `GET /login/claude` to `server.py`: polls `_claude_login_pending` and the login container for completion; on complete writes `ga-claude-auth` and returns `{"status": "complete"}`; returns `{"status": "pending", "login_url"}` while waiting; returns 404 if no flow is pending
- [ ] 2.3 Add `POST /logout/claude` to `server.py`: deletes `ga-claude-auth`, wipes `~/.claude/` from all running Claude-backend crews via `container_exec`, returns 409 if not authenticated

## 3. Crew Auth Injection

- [ ] 3.1 Add `_inject_claude_auth(podman, container)` to `lifecycle.py`: untar `ga-claude-auth` into the crew container's `~/.claude/` using `container_exec` or `podman cp`
- [ ] 3.2 In `_finish_crew_setup`, extend the Claude backend branch: if `GA_CREW_ANTHROPIC_API_KEY` is set use the existing env var path; else if `ga-claude-auth` exists call `_inject_claude_auth`; else this is unreachable (launch blocks before reaching setup)
- [ ] 3.3 In `launch()` in `server.py`, extend the Claude auth check: if `GA_CREW_ACP_BACKEND=claude` and `GA_CREW_ANTHROPIC_API_KEY` is unset and `ga-claude-auth` is missing/empty, call `_initiate_claude_login` and return `not_authenticated` with the login URL

## 4. Startup Validation Relaxation

- [ ] 4.1 Remove the `_validate_claude_api_key` call from `Config.validate()` in `config.py` (or make it a no-op) — the API key is no longer required at startup when OAuth is an alternative
- [ ] 4.2 Update `ghostship.conf.example` and `docs/configuration.md` to reflect that `GA_CREW_ANTHROPIC_API_KEY` is optional when using Claude OAuth login

## 5. Startup Cleanup

- [ ] 5.1 Add `ga-claude-login-*` container sweep to `_reconcile_registry` (mirrors the `ga-login-*` sweep), so orphaned Claude login containers are cleaned up on transport restart

## 6. Tests

- [ ] 6.1 Unit test: `POST /login/claude` returns 200 + login_url when unauthenticated; 409 when already authenticated; 409 when flow in progress
- [ ] 6.2 Unit test: `GET /login/claude` returns pending/complete states correctly; 404 when no flow
- [ ] 6.3 Unit test: `POST /logout/claude` clears `ga-claude-auth` and calls container wipe for running Claude crews; 409 when not authenticated
- [ ] 6.4 Unit test: `_finish_crew_setup` Claude branch — API key path injects env var; OAuth path calls `_inject_claude_auth`; neither-present path is not reachable from setup (guarded by launch)
- [ ] 6.5 Unit test: `launch()` with Claude backend and no credentials calls `_initiate_claude_login` and returns `not_authenticated`
- [ ] 6.6 Unit test: `Config.validate()` no longer raises for `GA_CREW_ACP_BACKEND=claude` without `GA_CREW_ANTHROPIC_API_KEY`

## 7. Docs

- [ ] 7.1 Add Claude OAuth login flow to `docs/auth.md` — how to authenticate, how to re-authenticate, how to logout
- [ ] 7.2 Update `docs/configuration.md` — `GA_CREW_ANTHROPIC_API_KEY` marked optional; note OAuth alternative
