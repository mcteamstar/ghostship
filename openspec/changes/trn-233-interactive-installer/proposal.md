# Proposal

**Plane ticket:** TRN-233

## Why

`install.sh` is non-interactive — operators must configure everything via `ghostship.conf` before running it, and authenticate separately afterwards. This creates friction for new installs: the README instructions span config, install, and auth as three separate steps, and it's easy to miss one. An interactive guided mode improves the first-run experience without changing the existing non-interactive path for operators who already have a `ghostship.conf`.

## What Changes

- **Interactive mode trigger**: when `install.sh` is run without a pre-existing `ghostship.conf` (or with `--setup` flag), enter a guided setup that walks through configuration, builds images, then authenticates.
- **Step 1 — Backend selection**: prompt to choose backend: `kiro` (default), `claude`, `codex`. Sets `GA_CREW_AGENT`.
- **Step 2 — Collect credentials**: for the chosen backend, prompt for required config (e.g. `KIRO_IDENTITY_PROVIDER`/`KIRO_REGION` for kiro; `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` for claude; `OPENAI_API_KEY` for codex).
- **Step 3 — Writes `ghostship.conf`**: save collected config so subsequent installs are non-interactive.
- **Step 4 — Build and start**: run the normal install pipeline.
- **Step 5 — Run login flow**: after transport is ready, trigger the appropriate login (`ghostship auth login` or equivalent). Display the URL/code, wait for completion. Operator finishes the install already authenticated.
- **Step 6 — Harness registration (optional)**: prompt to run `ghostship setup` to wire MCP server into detected harnesses (kiro-cli, Claude Code, opencode).
- **Non-goals**: no TUI, no multi-backend setup in interactive mode (stretch goal), existing non-interactive path unchanged.

## Capabilities

### New Capabilities

- `installation/interactive-setup`: requirements for the guided setup flow — detection of missing conf, backend selection prompt, credential collection, conf write, post-install login, harness registration offer.

### Modified Capabilities

- `installation`: note that `install.sh` supports both interactive (no conf) and non-interactive (conf present) modes.

## Impact

- `scripts/install.sh` — interactive mode detection and prompt functions
- `docs/configuration.md` and `README.md` — document the interactive path
- No transport code changes
