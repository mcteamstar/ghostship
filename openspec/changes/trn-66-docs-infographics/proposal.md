## Why

Colleague demos revealed that ghostship's value and usage pattern aren't immediately apparent from the current README — the text explains it but a visual makes it click instantly. Two things specifically need pictures: where ghostship sits relative to the wider AI toolchain, and the basic loop of how you actually use it day-to-day. The same clarity gap affects agents picking up the `ghostship` MCP tools for the first time: tool descriptions don't signal workflow order, and the plugin skill files don't make the setup or operational path obvious enough to follow without reaching for the docs.

## What Changes

**Visual documentation (docs/):**
- Generate 2 infographics for the root README:
  - **Architecture diagram** — where ghostship fits: harness (Admiral) → ghostship MCP → transport → crew containers (KiroCrew) → agents; how it relates to Claude/Kiro/other harnesses
  - **Usage flow diagram** — the basic operational loop: install → connect → launch crew → dispatch task → pickup result → nuke when done
- Generate 3 diagrams for `docs/` pages:
  - **Fleet/crew mental model** — Admiral, fleet, ghostship, crew, Captain, agents hierarchy (for `docs/architecture.md`)
  - **SDD workflow** — Spectre → Ghost → Banshee → Reaper cycle with Captain/Raven orchestration (for `docs/architecture.md`)
  - **Agent roles overview** — the six personas in one visual showing what each owns in the workflow (for `docs/agents.md`)
- Integrate all images into README and relevant `docs/` pages with appropriate placement and captions
- All images generated stored in `docs/images/`

**Tool descriptions (`transport/server.py`):**
- Revise the docstrings for `launch`, `supply`, `evac`, `dispatch`, `pickup`, `steer`, `nuke`, and `captain` to reinforce the intended workflow order (launch → supply → dispatch → pickup → steer → nuke) and make relationships between tools explicit
- The top-level MCP server `description=` field should also reflect the workflow framing

**Plugin skill files (`.claude-plugin/skills/`):**
- `ghostship-admin/SKILL.md` — make the setup path more direct: clearer prerequisite order, auth-before-launch guardrail more prominent, and the handoff to `ghostship-command` crisper
- `ghostship-command/SKILL.md` — make the operational flow clearer for a first-time reader: fleet lifecycle order explicit in the mental model, SDD workflow with Captain/Raven surfaced earlier and more concisely

## Capabilities

### New Capabilities

- `agent-skill-contracts`: The `.claude-plugin/skills/` files define the agent-facing contract for how a client-side agent picks up and uses ghostship — their description front-matter and content are a spec-level surface (clarity, completeness, and correct workflow order). This change establishes that contract as something spec-tracked.

### Modified Capabilities

- `mcp-server`: Tool descriptions are part of the MCP tool surface — they shape how agents interpret and sequence tool calls. This change updates the requirement that tool descriptions reinforce the intended workflow order and make tool relationships explicit (currently the spec only tracks tool existence and grouping, not description content).

## Impact

- `docs/images/` — 5 new static image files
- `README.md` — 2 new diagrams inserted into appropriate sections
- `docs/architecture.md` — fleet/crew model and SDD workflow diagrams
- `docs/agents.md` — agent roles overview diagram
- `transport/server.py` — revised tool docstrings for the 8 core tools + server description
- `.claude-plugin/skills/ghostship-admin/SKILL.md` — revised for setup clarity
- `.claude-plugin/skills/ghostship-command/SKILL.md` — revised for operational flow clarity
- `openspec/changes/trn-66-docs-infographics/specs/` — delta specs for `mcp-server` and new `agent-skill-contracts`
