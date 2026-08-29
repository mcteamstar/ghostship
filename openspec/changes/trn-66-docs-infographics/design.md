## Context

See `proposal.md - Why` for motivation. This change touches three distinct surfaces:

1. **Static images** (`docs/images/`) — generated via image generation, integrated into `README.md`, `docs/architecture.md`, and `docs/agents.md`
2. **Tool descriptions** (`transport/server.py`) — docstrings on the 8 core MCP tools + the server-level description
3. **Plugin skill files** (`.claude-plugin/skills/`) — `ghostship-admin/SKILL.md` and `ghostship-command/SKILL.md`

Existing style reference: six agent portrait PNGs in `docs/images/` (`agent-ghost.png`, `agent-spectre.png`, etc.) establish the dark/tech/military visual aesthetic to match. The `ghostship.png` hero image is a second reference point.

The `.claude-plugin/skills/` directory is explicitly not copied into crews — it is client-side-only context for whoever holds the MCP connection. Its content is an agent-facing contract, not implementation code.

---

## Goals / Non-Goals

**Goals:**
- Five generated infographics that communicate distinct concepts at a glance (no one image tries to say everything)
- Tool docstrings that make workflow order and tool relationships explicit for an agent reading them cold
- Skill files that let an agent follow the correct setup or operational path without consulting `docs/`
- Delta specs that record the new spec-level requirements added by the tool description and skill contract changes

**Non-Goals:**
- Animated or interactive diagrams — static PNG only
- Changes to actual tool behavior, API signatures, or agent prompt content
- Overhauling the README narrative prose (image insertion only, no prose rewrites)
- Updating the six agent portrait images

---

## Decisions

### D1 — Five focused images rather than one composite

**Decision:** One image per concept (architecture placement, usage flow, fleet hierarchy, SDD cycle, agent roles). No single "everything" diagram.

**Rationale:** Each image serves a different audience moment — the architecture placement image is for someone evaluating ghostship, the usage flow is for someone starting their first session, the SDD workflow is for someone wiring up Captain. Compositing them degrades each message. Separate images can also be reused individually in docs, README, and future blog posts without cropping.

**Alternative considered:** A two-panel or split-image approach for the README (one horizontal banner). Rejected: too wide for most GitHub README widths at a readable size.

### D2 — Image generation for visual consistency, not code-drawn diagrams

**Decision:** Use image generation for all five images.

**Rationale:** The existing agent portraits set a dark/tech/military aesthetic that code-drawn tools (Mermaid, Excalidraw, Graphviz) cannot match. Visual consistency with the established identity is the goal; the infographics are meant to feel like they belong with the portraits, not like a different product. Image generation gives direct control over style.

**Alternative considered:** Mermaid or Excalidraw for the flow/hierarchy diagrams. Rejected for the README images (wrong aesthetic) but worth noting as a fallback if image generation is unavailable — the architecture and usage flow diagrams are the highest-priority README additions and a clean code-drawn alternative is acceptable there if style consistency cannot be achieved.

### D3 — Image filenames and storage

**Decision:** Store in `docs/images/` with descriptive kebab-case names:
- `arch-system-placement.png` — harness → transport → crew → agents
- `usage-flow.png` — install → connect → launch → dispatch → pickup → nuke
- `fleet-crew-hierarchy.png` — Admiral → fleet → crew → Captain → agents
- `sdd-workflow.png` — Spectre → Ghost → Banshee → Reaper with Raven/Captain
- `agent-roles-overview.png` — six personas, what each owns

**Rationale:** `docs/images/` is the established convention (all existing images are there). Descriptive names make the file's subject immediately clear in git history and image references.

### D4 — README insertion points

**Decision:**
- `arch-system-placement.png` — insert after the introductory paragraph ("A multi-agent orchestration system...") and before the "Why Ghostship?" section
- `usage-flow.png` — insert at the top of the "MCP Tools" table section, just before the tools table

**Rationale:** The architecture placement image answers "what is this?" as early as possible for a first-time reader. The usage flow sits next to the tools table because that's where the operational sequence lives and the visual directly annotates it. Inserting earlier would front-load the README too heavily.

**Markdown to use:**
```markdown
![Ghostship architecture: harness → transport → crews → agents](docs/images/arch-system-placement.png)
```
```markdown
![Usage flow: install → connect → launch → dispatch → pickup → nuke](docs/images/usage-flow.png)
```

### D5 — docs/ insertion points

**Decision:**
- `fleet-crew-hierarchy.png` — insert at the top of `docs/architecture.md`, before the "## Components" section
- `sdd-workflow.png` — insert in `docs/architecture.md` after the "## Ghost Academy" section (which describes the Spectre → Ghost → Banshee → Reaper workflow in prose)
- `agent-roles-overview.png` — insert in `docs/agents.md` after the agents table and before the prose paragraph that follows it

**Rationale:** Each image sits directly adjacent to its corresponding prose explanation so readers encounter the visual immediately before or after the text it illustrates. Inserting at the very top of architecture.md would be premature before the reader has any context; after the intro sections is the right placement for the hierarchy image.

**Markdown to use:**
```markdown
![Fleet and crew hierarchy: Admiral → fleet → ghostship → crew → Captain → agents](docs/images/fleet-crew-hierarchy.png)
```
```markdown
![SDD workflow: Spectre → Ghost → Banshee → Reaper, with Raven/Captain orchestration](docs/images/sdd-workflow.png)
```
```markdown
![Agent roles: the six personas and what each owns in the OpenSpec workflow](docs/images/agent-roles-overview.png)
```

### D6 — Image generation prompt strategy

The agent portrait images establish the reference aesthetic: dark backgrounds (near-black), cool blue/teal accent lighting, high-contrast, military/tech feeling, moody atmosphere. Each infographic must feel like it belongs in the same product.

General prompt structure for all five images:
```
<subject description>, dark background, deep navy and black tones, cyan and electric blue accent lighting,
technical diagram aesthetic, military intelligence briefing style, high contrast, sharp edges,
clean typography labels, ghostship specops aesthetic, professional infographic, dark tech art
```

Per-image subjects:
- **arch-system-placement**: layered horizontal flow diagram, three tiers labeled "Harness (Admiral)", "ghostship MCP transport", "KiroCrew crew containers", with upward arrows showing command flow and downward arrows showing results
- **usage-flow**: circular or linear six-step loop labeled install → connect → launch → dispatch → pickup → nuke, each step as a glowing node with a brief icon
- **fleet-crew-hierarchy**: vertical tree diagram, Admiral at top, fleet spanning multiple crew nodes below, each crew showing Captain → worker agent personas
- **sdd-workflow**: circular pipeline: Spectre (plan) → Ghost (implement) → Banshee (review) → Reaper (close), with Raven and Captain shown as the outer orchestration ring
- **agent-roles-overview**: six-panel grid, one cell per persona, each showing the persona name, avatar silhouette style, and a two-word role label

**Negative prompts for all:** `photorealistic, human faces, logos, bright white backgrounds, cartoon, sketch`

### D7 — Tool description revision approach

**Decision:** Revise docstrings in-place; do not restructure function signatures. Keep the "Also: ..." alias lines (they serve model tool selection). Add explicit "Step N of the workflow:" framing to the first line of the core tools where it aids understanding.

**Revised framing for each tool:**
- `crews` — situational awareness: see what's running before you act
- `launch` — step 1: create a crew workspace (prerequisite for all dispatch work)
- `supply` — step 2: seed the workspace with a repo or files (required before any repo-touching dispatch)
- `dispatch` — step 3: send a task to an agent persona; returns task_id
- `pickup` — step 4: check progress or collect the result; also use to list all tasks
- `steer` — step 4b: redirect a running task or continue a completed session
- `evac` — step 5: extract results, diffs, or a git bundle from the workspace
- `nuke` — step 6: destroy the crew and both volumes when work is done (evac first)
- `captain` — autopilot: hands the full SDD cycle to a Raven check-in loop

**Decision:** Also update the server-level `description=` to reflect the workflow framing: replace the current `"Ghost Academy crew orchestration: launch workspaces, dispatch agents, evac results, nuke crews"` with something that names the workflow sequence explicitly.

**Alternative considered:** A separate tool named `workflow_guide` that returns a text description of the sequence. Rejected: adds surface area and requires a tool call; docstring framing costs nothing and is seen in the tool list automatically.

### D8 — Skill file revision approach

**Decision:** Revise in-place (same filenames, same structure). Do not rewrite from scratch.

**ghostship-admin/SKILL.md changes:**
- Move the auth-before-launch warning into a prominent callout block at the top of the "Install" section, not buried in the login section
- Clarify the setup sequence as an explicit numbered flow: (1) install Podman, (2) run `./install.sh`, (3) complete `/login` flow, (4) register MCP client, (5) switch to ghostship-command
- The handoff sentence to `ghostship-command` should appear at the end of step 4, not only in the file header

**ghostship-command/SKILL.md changes:**
- Add an explicit "Intended workflow order" line to the mental model section (launch → supply → dispatch → pickup/steer → evac → nuke) before the per-step detail
- Surface the autopilot (Captain) path in the mental model overview, not only in a later section — first-time readers skip to the mental model and miss it
- The "Discover before assuming anything" section stays; ensure it's clearly framed as step 0

**Alternative considered:** Merging both skills into one. Rejected: the admin/command split is a meaningful and correct boundary — admin is shell-only setup with no MCP connection, command is MCP-connected fleet driving. Merging makes a skill that's either always too long or always missing something.

---

## Risks / Trade-offs

**[Risk] Image generation output requires iteration to hit the right aesthetic** → The first generation run may not match the agent portrait style closely enough. Mitigation: use the existing portraits as style references in the prompt (provide their filenames for the tool to reference), budget 2–3 generation attempts per image before accepting the best result.

**[Risk] Image sizes are large (existing portraits are 120–145 KB each)** → Five new images add ~600–700 KB to the repo. Mitigation: this is acceptable for a docs-only repo like ghostship. If repo size becomes a concern, they can be moved to Git LFS later without changing any markdown references.

**[Risk] README image widths may be too large on narrow GitHub viewports** → Mitigation: do not set explicit `width=` attributes on the README images; let GitHub's responsive layout scale them. For the docs pages, also leave width unset.

**[Risk] Tool description changes must not alter behavior** → Docstring revisions are purely text; no logic is touched. Mitigation: the tasks explicitly scope each docstring change and the spec delta documents the new requirement without altering any scenario that tests behavior.

**[Risk] Skill file edits may introduce drift from docs/** → The skill files explicitly tell readers to trust `docs/` over the skill for anything not covered. Mitigation: the revision approach (D8) does not add new factual claims — it restructures and re-emphasizes existing content, so drift risk is low.

---

## Migration Plan

This change is fully additive and requires no migration:
- New image files can be added without touching any other path
- Docstring changes take effect on the next transport deploy (`./install.sh` for transport, `nuke` + `launch` not needed for docstrings)
- Skill file changes take effect immediately for any agent that picks them up in a new session
- Delta specs are tracked in the change's `specs/` directory and synced to `openspec/specs/` by Reaper at archive time

Rollback: revert the commit. No runtime state to unwind.
