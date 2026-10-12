#!/bin/sh
# OpenCode agent toolchain. Run by the spec-ops image build when "opencode" is
# in AGENT_TOOLCHAINS (from GA_CREW_AGENT). Installs ONE package:
#   opencode-ai@1.18.30 — the `opencode` CLI binary (anomalyco/opencode, npm: opencode-ai),
#     which ships its own `opencode acp` subcommand (the ACP server KiroCrew's
#     AcpClient spawns for acp_backend="opencode" sessions).
#     Version 1.18.30 is the version tested against KiroCrew 0.9.0 (acp/harness/opencode.py).
#
# Unlike Claude (which needs claude-agent-acp AND the separate `claude` CLI) and
# Codex (which uses the standalone codex-acp adapter), OpenCode ships the ACP
# server inside the main package — there is no separate ACP adapter to install.
#
# Login / headless behaviour: opencode reads its credentials from
#   ~/.local/share/opencode/auth.json  (written by `opencode auth login`).
# ghostship drives the login in an ephemeral ga-opencode-login-* container
# (spec-ops image), captures the resulting ~/.local/share/opencode/ as the
# ga-opencode-auth tar, and untars it into the crew container at launch —
# structurally identical to the Claude ga-claude-auth flow. OpenCode is Preview
# status in KiroCrew and requires Developer Mode on the gateway.
set -eu
npm install -g opencode-ai@1.18.30
