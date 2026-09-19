## ADDED Requirements

### Requirement: Codex backend tool approval model is documented and enforced

When `GA_CREW_ACP_BACKEND=codex`, ghostship's per-call kiro approval gate does not apply — the `codex-acp` adapter drives its own session. KiroCrew's ACP tool gate SHALL verify that the Codex session advertised `mode=read-only` at `session/new` and apply it before the first prompt, refusing the session otherwise, so the PreToolUse gate is armed for the calls the adapter makes. The signed security policy ceiling (`commands.deny` in `security_policy.json`) SHALL remain enforced at the gateway level regardless of backend.

Because ACP v1 offers no way for an adapter to declare a passive READ, the sensitive-path read block cannot observe reads the Codex adapter performs. The compensating control is an OS-boundary credential mask: the adapter's own credential home (`~/.codex/auth.json`) and equivalent env-override roots SHALL be hidden from the adapter's child process, so a read the gate cannot see still cannot reach the fleet's other credentials.

The `crew-governance` spec and `docs/architecture.md` SHALL document this model: Codex crews bypass the per-call approval gate, run under a verified read-only ACP mode, remain subject to the signed policy ceiling, and rely on the credential-dir OS mask as the compensating control for the ACP-v1 read-visibility gap.

#### Scenario: Codex session refused when not read-only
- **WHEN** a Codex-backend crew's `session/new` does not advertise `mode=read-only`
- **THEN** the ACP tool gate refuses the session before the first prompt rather than proceeding with an unverified mode

#### Scenario: KiroCrew governance ceiling still enforced for Codex crews
- **WHEN** an agent running on the Codex backend attempts a command matching `commands.deny` in the crew's `security_policy.json`
- **THEN** the KiroCrew gateway rejects the command regardless of backend — the policy ceiling is enforced at the gateway level, not the ACP client level

#### Scenario: Codex adapter cannot reach other credential homes
- **WHEN** a Codex-backend crew session runs
- **THEN** the adapter's child process cannot read `~/.codex/auth.json` (its own token store) nor the standard-tier credential homes; those directories are masked at the OS boundary

#### Scenario: Governance model documented in architecture docs
- **WHEN** an operator reads `docs/architecture.md`
- **THEN** they find a note explaining that Codex crews bypass ghostship's per-call approval gate, run under a verified read-only ACP mode, remain subject to the signed policy ceiling, and that the credential-dir OS mask compensates for the ACP-v1 read-visibility gap
