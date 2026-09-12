# Agent Skill Contracts — Delta Spec (trn-66-docs-infographics)

Adds the `agent-skill-contracts` capability.

## Context

The `.claude-plugin/skills/` files (`ghostship-admin/SKILL.md` and
`ghostship-command/SKILL.md`) are client-side-only context: they are never
copied into a crew — they are read by whoever holds the MCP connection. That
makes their content an agent-facing **contract**, not implementation code. An
agent picks up ghostship by reading these files, and if their front-matter
misstates their scope, or their setup/operational flow can only be followed by
also opening `docs/`, or the boundary between the two files is unclear, the
agent takes the wrong path or stalls.

This capability has never been spec-tracked. The two skill files' clarity,
completeness, and correct workflow framing were treated as prose to be edited
ad hoc. This delta establishes them as a spec-level surface with explicit
requirements, so future edits are held to a stated contract rather than
subjective judgment.

The requirements below govern skill-file **content and structure**. They do not
govern the runtime behavior of any tool, the agent prompt content, or anything
copied into a crew — the skill files are explicitly excluded from crew images.

## ADDED Requirements

### Requirement: Skill description front-matter accurately reflects scope

Each file in `.claude-plugin/skills/` SHALL carry description front-matter whose
stated scope matches what the file actually covers, so an agent selecting a
skill from its description alone lands in the right file. The two skills own
distinct, non-overlapping halves of the lifecycle: `ghostship-admin` is
shell-only setup with no MCP connection; `ghostship-command` is MCP-connected
fleet driving. Neither description SHALL claim scope that belongs to the other.

#### Scenario: Admin skill description scoped to setup

- **WHEN** an agent reads the `ghostship-admin/SKILL.md` description front-matter
- **THEN** it describes shell-only installation and setup (prerequisites,
  install, auth, MCP client registration) and does not claim to cover
  MCP-connected fleet operation

#### Scenario: Command skill description scoped to operation

- **WHEN** an agent reads the `ghostship-command/SKILL.md` description
  front-matter
- **THEN** it describes MCP-connected fleet driving (launch → supply → dispatch
  → pickup/steer → evac → nuke, plus the Captain autopilot) and does not claim
  to cover the shell-only install/auth steps

### Requirement: Setup and operational flow is followable without consulting docs/

Each skill file SHALL contain the ordered steps needed to complete its own flow
without the reader having to open anything under `docs/`. `docs/` remains the
authoritative reference for detail not carried in the skill, and a skill MAY
point to it, but the primary path SHALL be self-contained.

For `ghostship-admin`, the setup path SHALL be an explicit ordered sequence:
install prerequisites → run the installer → complete the auth flow → register
the MCP client, with the auth-before-launch guardrail presented as a prominent
callout rather than buried.

For `ghostship-command`, the operational path SHALL state the intended workflow
order (launch → supply → dispatch → pickup/steer → evac → nuke) in the mental
model before the per-step detail, surface the Captain autopilot in that same
mental-model overview, and frame the "discover before assuming anything"
guidance as the pre-work step 0.

#### Scenario: Admin setup path is a self-contained ordered sequence

- **WHEN** an agent follows `ghostship-admin/SKILL.md` to set up ghostship
- **THEN** it can complete install → auth → MCP registration in order using only
  the skill file, and the auth-before-launch guardrail is visible as a callout
  before the launch step

#### Scenario: Command mental model states workflow order up front

- **WHEN** an agent reads the mental-model section of `ghostship-command/SKILL.md`
- **THEN** the intended workflow order and the Captain autopilot path are both
  present in that overview, before the per-step detail, and the discover step is
  labeled as step 0

#### Scenario: docs/ is reference, not a required detour

- **WHEN** an agent follows either skill's primary flow
- **THEN** it does not need to open any `docs/` page to complete that flow, even
  though the skill may reference `docs/` for additional detail

### Requirement: Each skill signals its handoff boundary to the other

Each skill file SHALL make explicit where its own responsibility ends and the
other skill begins, so an agent knows when to switch files rather than
improvising outside the current skill's scope.

`ghostship-admin` SHALL end its setup sequence with a handoff sentence pointing
to `ghostship-command` for fleet operation. `ghostship-command` SHALL make clear
that install/auth setup is `ghostship-admin`'s responsibility and is a
prerequisite already completed before its own flow begins.

#### Scenario: Admin hands off to command at the end of setup

- **WHEN** an agent completes the MCP-registration step in
  `ghostship-admin/SKILL.md`
- **THEN** the skill directs it to `ghostship-command` for driving the fleet

#### Scenario: Command points back to admin for setup

- **WHEN** an agent reading `ghostship-command/SKILL.md` has not completed setup
- **THEN** the skill makes clear that install/auth/registration belong to
  `ghostship-admin` and are a prerequisite for the operational flow

## Non-Goals

- Governing runtime tool behavior, agent prompt content, or anything copied into
  a crew image — the skill files are client-side-only and excluded from crews.
- Merging the two skills into one; the admin/command (shell-setup vs
  MCP-connected operation) split is the correct boundary this contract preserves.
- Adding new factual claims to the skills beyond restructuring and re-emphasizing
  existing content.
