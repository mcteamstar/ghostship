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
# Headless tool approvals: Claude crews run in KiroCrew's `default` mode under
# its hook gate. KiroCrew does not write `bypassPermissions`; the
# `dangerously_skip_permissions` setting only approves calls that the gate
# allows and cannot override a gate denial.
set -eu
npm install -g @agentclientprotocol/claude-agent-acp@0.79.0
npm install -g @anthropic-ai/claude-code@2.1.293
