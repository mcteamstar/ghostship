#!/bin/sh
# Codex agent toolchain. Run by the spec-ops image build when "codex" is in
# AGENT_TOOLCHAINS (from GA_AGENT_BACKENDS). Installs ONE package:
#   @agentclientprotocol/codex-acp@1.12.0 — the ACP server binary that
#     KiroCrew's AcpClient spawns for acp_backend="codex" sessions.
#
# The adapter includes a compatible Codex CLI dependency. Expose that exact
# binary on PATH for both the adapter's app-server spawn and device login.
# Do not install a second independently versioned CLI.
#
# Login / headless behaviour: codex-acp reads its credentials from
#   ~/.codex/auth.json  (relocatable via the CODEX_HOME env var).
# Two auth paths are supported:
#   - API key: the OPENAI_API_KEY env var (injected at crew-container creation
#     from OPENAI_API_KEY) authenticates without any login flow.
#   - OAuth (ChatGPT subscription): a device / browser sign-in that writes
#     ~/.codex/auth.json. ghostship drives this in an ephemeral
#     ga-codex-login-* container (spec-ops image), captures the resulting
#     ~/.codex/ as the ga-codex-auth tar, and untars it into the crew
#     container's ~/.codex/ at launch.
# OPENAI_BASE_URL redirects codex-acp to an OpenAI-compatible endpoint.
set -eu
npm install -g @agentclientprotocol/codex-acp@1.12.0

ln -sf "$(npm root -g)/@agentclientprotocol/codex-acp/node_modules/.bin/codex" /usr/local/bin/codex
codex --version
