#!/bin/sh
# Claude Code agent toolchain. Run by the spec-ops image build when "claude" is
# in AGENT_TOOLCHAINS (from GA_AGENT_BACKENDS). Installs TWO packages:
#   @agentclientprotocol/claude-agent-acp@0.79.0  — the ACP server binary
#     (the `claude-agent-acp` binary that KiroCrew's AcpClient spawns for
#     acp_backend="claude" sessions)
#   @anthropic-ai/claude-code@2.1.293  — the `claude` CLI binary
#     (required by claude-agent-acp via CLAUDE_CODE_EXECUTABLE; the ACP
#     server delegates model turns to the Claude Agent SDK which needs this)
#
# Headless tool-approval suppression: KiroCrew writes
# <work_dir>/.claude/settings.local.json with permissions.defaultMode set to
# "bypassPermissions" at session spawn time (see kiro_crew/acp/client.py
# _write_claude_local_settings). No environment variable override is needed
# from the ghostship side — KiroCrew handles it automatically via the
# dangerously_skip_permissions config key already set in _patch_crew_config.
set -eu
npm install -g @agentclientprotocol/claude-agent-acp@0.79.0
npm install -g @anthropic-ai/claude-code@2.1.293
