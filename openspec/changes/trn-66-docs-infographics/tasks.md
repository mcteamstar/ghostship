## 1. Delta Specs

- [ ] 1.1 Write `specs/mcp-server/spec.md` — delta spec adding the requirement that tool descriptions reinforce workflow order and make tool relationships explicit (covers the revised docstrings for the 8 core tools and the server-level description)
- [ ] 1.2 Write `specs/agent-skill-contracts/spec.md` — new capability spec defining the `.claude-plugin/skills/` files as an agent-facing contract surface: description front-matter must accurately reflect scope, setup/operational flow must be followable without consulting `docs/`, and each file must clearly signal its handoff boundary to the other

## 2. Visual Infographics — Generate Images

- [ ] 2.1 Read `docs/images/agent-ghost.png` and `docs/images/agent-spectre.png` as style references, then generate `docs/images/arch-system-placement.png` — layered horizontal flow diagram showing harness (Admiral) → ghostship MCP transport → KiroCrew crew containers → agents, dark navy/black background with cyan accent lighting (see design.md D6 for full prompt guidance)
- [ ] 2.2 Generate `docs/images/usage-flow.png` — six-step circular or linear loop: install → connect → launch → dispatch → pickup → nuke, each step as a glowing node with a brief label (same dark tech aesthetic)
- [ ] 2.3 Generate `docs/images/fleet-crew-hierarchy.png` — vertical tree diagram: Admiral at top, fleet spanning multiple crew nodes below, each crew showing Captain → worker agent personas
- [ ] 2.4 Generate `docs/images/sdd-workflow.png` — circular SDD pipeline: Spectre (plan) → Ghost (implement) → Banshee (review) → Reaper (close), with Raven and Captain shown as the outer orchestration ring
- [ ] 2.5 Generate `docs/images/agent-roles-overview.png` — six-panel grid, one cell per persona, each showing persona name, silhouette-style avatar, and a two-word role label

## 3. Visual Infographics — Insert into Docs

- [ ] 3.1 Insert `arch-system-placement.png` into `README.md` — after the introductory paragraph ("A multi-agent orchestration system...") and before the "## Why Ghostship?" heading, using: `![Ghostship architecture: harness → transport → crews → agents](docs/images/arch-system-placement.png)`
- [ ] 3.2 Insert `usage-flow.png` into `README.md` — at the start of the "### MCP Tools" section, immediately before the tools table, using: `![Usage flow: install → connect → launch → dispatch → pickup → nuke](docs/images/usage-flow.png)`
- [ ] 3.3 Insert `fleet-crew-hierarchy.png` into `docs/architecture.md` — immediately before the "## Components" heading, using: `![Fleet and crew hierarchy: Admiral → fleet → ghostship → crew → Captain → agents](docs/images/fleet-crew-hierarchy.png)`
- [ ] 3.4 Insert `sdd-workflow.png` into `docs/architecture.md` — immediately after the "## Ghost Academy" section's closing paragraph (after "See [agents.md](agents.md) for what each persona owns..."), using: `![SDD workflow: Spectre → Ghost → Banshee → Reaper, with Raven/Captain orchestration](docs/images/sdd-workflow.png)`
- [ ] 3.5 Insert `agent-roles-overview.png` into `docs/agents.md` — after the agents table and before the paragraph beginning "The five worker personas form the OpenSpec cycle...", using: `![Agent roles: the six personas and what each owns in the OpenSpec workflow](docs/images/agent-roles-overview.png)`

## 4. Tool Descriptions — transport/server.py

- [ ] 4.1 Update the server-level `description=` field in the `MCPServer(...)` constructor — replace `"Ghost Academy crew orchestration: launch workspaces, dispatch agents, evac results, nuke crews"` with a description that names the workflow sequence explicitly: launch a crew → supply a repo → dispatch tasks to agents → pickup results → steer if needed → evac output → nuke when done
- [ ] 4.2 Update `crews()` docstring — frame it as situational awareness: check what crews and tasks are running before deciding what to do next
- [ ] 4.3 Update `launch()` docstring — add explicit "Step 1: create a crew workspace" framing; reinforce that `supply` must follow before any repo-touching dispatch; keep the auth-fallback description
- [ ] 4.4 Update `supply()` docstring — add "Step 2: seed the workspace" framing; make the "dispatch into an empty crew is a real failure mode" guardrail explicit in the docstring (currently only in ghostship-command/SKILL.md)
- [ ] 4.5 Update `dispatch()` docstring — add "Step 3: send a task to an agent persona" framing; clarify that the agent has zero context beyond the `task` string; note that `pickup` is the next step
- [ ] 4.6 Update `pickup()` docstring — add "Step 4: check progress or collect the result" framing; note the relationship to `steer` (use steer to redirect mid-flight or continue a completed session)
- [ ] 4.7 Update `steer()` docstring — add "Step 4b: redirect a running task or continue a completed session" framing; clarify the running-vs-completed distinction upfront
- [ ] 4.8 Update `evac()` docstring — add "Step 5: extract results, diffs, or a git bundle" framing; note it pairs with `supply` as the complete file exchange protocol
- [ ] 4.9 Update `nuke()` docstring — add "Step 6: destroy the crew and both volumes when work is done" framing; emphasize that `evac` must come first (irreversible)
- [ ] 4.10 Update `captain()` docstring — add "Autopilot: hand the full SDD lifecycle to a recurring Raven check-in" framing; clarify the relationship between the manual relay (dispatch/pickup/steer yourself) and the captain autopilot

## 5. Plugin Skill Files

- [ ] 5.1 Revise `ghostship-admin/SKILL.md` — restructure the install section as an explicit numbered setup sequence: (1) install Podman prerequisites, (2) run `./install.sh`, (3) complete the `/login` auth flow (promote the "do this before your first launch" warning to a visible callout), (4) register the MCP client; add a clear handoff sentence at the end of step 4 pointing to `ghostship-command`
- [ ] 5.2 Revise `ghostship-command/SKILL.md` — add an explicit "Intended workflow order: launch → supply → dispatch → pickup/steer → evac → nuke" line to the mental model section before the per-step detail; surface the Captain autopilot path in the mental model overview (currently only in a later section); ensure the "Discover before assuming anything" block is clearly labeled as the pre-work step 0

## 6. Verification

- [ ] 6.1 Confirm all 5 images exist in `docs/images/` and are non-empty PNG files
- [ ] 6.2 Confirm all 5 image markdown references render correctly (no broken paths — check filenames match exactly)
- [ ] 6.3 Confirm `README.md` still passes a markdown lint check (no broken headings or table formatting from the insertions)
- [ ] 6.4 Confirm `transport/server.py` is syntactically valid Python after docstring edits (`python3 -m py_compile transport/server.py`)
- [ ] 6.5 Confirm the two delta specs exist at `openspec/changes/trn-66-docs-infographics/specs/mcp-server/spec.md` and `openspec/changes/trn-66-docs-infographics/specs/agent-skill-contracts/spec.md`
- [ ] 6.6 Run `openspec status --change trn-66-docs-infographics` and confirm planning is complete (all artifacts green)
