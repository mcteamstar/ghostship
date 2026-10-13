# Tasks

## 1. Detection and mode switching

- [ ] 1.1 In `scripts/install.sh`, add detection logic at the top of the main flow: if no `ghostship.conf` is found (checking both `./ghostship.conf` and `./config/ghostship.conf`) OR `--setup` flag is passed, call `_interactive_setup` before the normal install pipeline. Ensure the normal path is completely unchanged when a conf exists. Verify: running `./install.sh` with an existing conf proceeds non-interactively; running without one enters interactive mode.

## 2. Prompt helpers and backend selection

- [ ] 2.1 Add a `_prompt` helper function that takes a prompt string, default value, and variable name, reads from stdin with `read -r -p`, and applies the default on empty input. Add a `_interactive_setup` function that uses `_prompt` to ask the operator to choose a backend (kiro/claude/codex) with kiro as default. Verify: selecting each backend sets `GA_CREW_AGENT` to the correct value.
- [ ] 2.2 Add credential collection prompts for each backend: kiro → `KIRO_IDENTITY_PROVIDER` and `KIRO_REGION`; claude → choice of `CLAUDE_CODE_OAUTH_TOKEN` (show instructions to run `claude setup-token` first) or `ANTHROPIC_API_KEY`; codex → `OPENAI_API_KEY` and optional `OPENAI_BASE_URL`. Verify: each backend path prompts for and collects the correct variables.

## 3. Write ghostship.conf

- [ ] 3.1 At the end of `_interactive_setup`, write collected values to `config/ghostship.conf` (creating `config/` if it doesn't exist). Only write non-empty collected values. Verify: after interactive setup, `config/ghostship.conf` contains the chosen `GA_CREW_AGENT` and credential vars; no blank lines or empty assignments are written.

## 4. Post-install login flow

- [ ] 4.1 After the transport reaches the "ready" health check in interactive mode, call the appropriate login flow for the selected backend. Display the login URL or device code and wait for the operator to complete auth. Reuse existing `_wait_for_login` / `_poll_login_status` infrastructure where it exists. Verify: the interactive flow ends with the transport authenticated; the operator does not need to run a separate `ghostship auth login`.

## 5. Harness registration prompt

- [ ] 5.1 After login completes in interactive mode, prompt the operator: "Register MCP server with detected harnesses? [y/N]". If yes, run `ghostship setup`. Verify: accepting registers the MCP server; declining skips it; either way the install exits cleanly.

## 6. Integration check

- [ ] 6.1 Run `tests/run.sh --unit` to confirm no regressions in existing install.sh unit tests. Manually verify the interactive flow end-to-end on a clean system (no conf present). Update `README.md` to mention the interactive first-run path.

## Workflow follow-up

- Archive the change after review.
