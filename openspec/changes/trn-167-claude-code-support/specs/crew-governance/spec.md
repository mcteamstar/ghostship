## ADDED Requirements

### Requirement: Claude backend tool approval gap is documented and mitigated

When `GA_CREW_ACP_BACKEND=claude`, KiroCrew's tool approval gate is bypassed (Claude Code sessions pass `dangerously_skip_permissions=True` to the ACP backend). However, Claude Code has its own internal tool approval layer that is separate from KiroCrew's gate. In a headless container context, Claude Code's internal approval prompts will stall the session indefinitely if they fire.

The transport SHALL configure Claude Code sessions to suppress interactive approval prompts when launching crew containers in Claude backend mode. This SHALL be achieved by injecting `CLAUDE_SKIP_TOOL_APPROVAL=true` (or the equivalent env var or CLI flag supported by `claude-agent-acp` for headless operation) into the crew container environment.

The `crew-governance` spec and `docs/architecture.md` SHALL document this gap: KiroCrew's governance ceiling (policy-enforced command denials) still applies to Claude Code crews, but KiroCrew's per-call tool approval gate does not.

#### Scenario: Claude crew does not stall on tool approval prompts
- **WHEN** a crew is launched with `GA_CREW_ACP_BACKEND=claude` and an agent task calls a tool
- **THEN** the tool executes without waiting for interactive approval; no stall occurs in a headless container

#### Scenario: KiroCrew governance ceiling still enforced for Claude crews
- **WHEN** an agent running on the Claude backend attempts a command matching `commands.deny` in the crew's `security_policy.json`
- **THEN** the KiroCrew gateway rejects the command regardless of backend — the policy ceiling is enforced at the gateway level, not the ACP client level

#### Scenario: Governance gap documented in architecture docs
- **WHEN** an operator reads `docs/architecture.md`
- **THEN** they find a note explaining that Claude Code crews bypass KiroCrew's per-call tool approval gate but remain subject to the signed security policy ceiling
