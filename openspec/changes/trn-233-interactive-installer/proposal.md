# Proposal

**Plane ticket:** TRN-233

## Why

`install.sh` is non-interactive — operators must configure everything via `ghostship.conf` before running it, and authenticate separately afterwards. This creates friction for new installs and makes multi-backend configuration opaque.

More importantly: the transport supports multiple agent backends simultaneously (`GA_CREW_AGENT=kiro,claude,codex`), meaning you can launch a kiro crew, a claude crew, and a codex crew all at once from the same transport — multiplexing across subscriptions and model providers per crew. But this capability is invisible in the current install flow. An operator following the README would never discover it.

An interactive guided mode surfaces this, reduces friction for first-run installs, and does not change the existing non-interactive path for operators who already have a `ghostship.conf`.

## What Changes

- **Interactive mode trigger**: when `install.sh` is run without a pre-existing `ghostship.conf` (or with `--wizard` flag) and stdin is a tty, enter a guided setup that walks through configuration, builds images, then authenticates.
- **Step 1 — Default backend**: prompt to choose the default agent backend (kiro/claude/codex). Sets the first entry of `GA_CREW_AGENT`.
- **Step 2 — Additional backends**: prompt for any additional backends to enable. Each adds a toolchain to the image build and makes that backend available for crew launch. Enables the kiro+claude+codex simultaneous crew topology.
- **Step 3 — Non-secret config per backend**: for kiro → `KIRO_IDENTITY_PROVIDER` and `KIRO_REGION`; for codex → `OPENAI_BASE_URL` (enables pointing at local litellm or any OpenAI-compatible proxy). Claude has no non-secret config at this stage.
- **Step 4 — Writes `ghostship.conf`**: save collected non-secret config. Secrets (API keys, OAuth tokens) are never written here — deferred to `ghostship auth login <backend>` (separate ticket).
- **Step 5 — Build and start**: run the normal install pipeline with all selected backends.
- **Step 6 — Auth**: for kiro, run `ghostship auth login` (device flow). For claude/codex, print instructions to run `ghostship auth login anthropic` / `ghostship auth login openai` once available (stubs for the next ticket).
- **Step 7 — Harness registration**: prompt to run `ghostship setup` to wire MCP server into detected harnesses.
- **Non-goals**: no TUI, existing non-interactive path unchanged, secret collection deferred to a follow-on ticket.

## Capabilities

### New Capabilities

- `installation/interactive-setup`: requirements for the guided setup flow — detection of missing conf, multi-backend selection, non-secret config collection, conf write, post-install login, harness registration offer.

### Modified Capabilities

- `installation`: note that `install.sh` supports both interactive (no conf) and non-interactive (conf present) modes, and that multiple backends can be active simultaneously.

## Impact

- `scripts/install.sh` — interactive mode detection, `_prompt` helper, `_interactive_setup` function
- `docs/configuration.md` and `README.md` — document interactive path and multi-backend topology
- No transport code changes
