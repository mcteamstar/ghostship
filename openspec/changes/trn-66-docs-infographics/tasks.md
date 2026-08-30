## 1. Delta Specs

- [ ] 1.1 Write `specs/mcp-server/spec.md` — delta spec adding the requirement that tool descriptions reinforce workflow order and make tool relationships explicit (covers the revised docstrings for the 8 core tools and the server-level description)
- [ ] 1.2 Write `specs/agent-skill-contracts/spec.md` — new capability spec defining the `.claude-plugin/skills/` files as an agent-facing contract surface: description front-matter must accurately reflect scope, setup/operational flow must be followable without consulting `docs/`, and each file must clearly signal its handoff boundary to the other

## 2. Image Generation Prompts

Image generation runs locally (ComfyUI on gpc), not inside the crew. Ghost's job here is to study the existing style and write ready-to-run prompts that will be executed externally.

- [ ] 2.0 Read `openspec/changes/archive/2026-08-29-trn-65-tool-images/design.md` — study the locked base prompt, negative prompt, per-tool prompt structure, and 512×512 px output spec used for the 10 tool images; this is the style reference for the 5 infographic images
- [ ] 2.1 Read the six existing agent images (`docs/images/agent-*.png`) and the hero image (`docs/images/ghostship.png`) to understand the established visual aesthetic
- [ ] 2.2 Write `openspec/changes/trn-66-docs-infographics/IMAGE_PROMPTS.md` — ready-to-run ComfyUI prompts for all 5 infographic images. For each image include:
  - Filename: `docs/images/<name>.png`
  - Positive prompt (extending the TRN-65 base prompt or using an adapted version appropriate for diagram/infographic style)
  - Negative prompt (same locked negative as TRN-65 unless a specific override is needed)
  - Output size (512×512 or wider if a diagram benefits from landscape)
  - Brief notes on what must read correctly at thumbnail size and any disambiguation rules (e.g. arch vs usage-flow must look different at 64px)

  The five images are (see design.md D3, D6 for context):
  - `arch-system-placement.png` — layered horizontal flow: harness → transport → crew containers → agents
  - `usage-flow.png` — six-step loop: install → connect → launch → dispatch → pickup → nuke
  - `fleet-crew-hierarchy.png` — vertical tree: Admiral → fleet → crew → Captain → agents
  - `sdd-workflow.png` — circular pipeline: Spectre → Ghost → Banshee → Reaper with Raven/Captain outer ring
  - `agent-roles-overview.png` — six-panel grid, one cell per persona

## 3. Visual Infographics — Insert into Docs

These tasks insert image references into docs. The image files will be generated and committed separately after the prompts are reviewed. Add the markdown references now with a note that the files will follow.

- [ ] 3.1 Insert `arch-system-placement.png` into `README.md` — after the introductory paragraph ("A multi-agent orchestration system...") and before the "## Why Ghostship?" heading, using: `![Ghostship architecture: harness → transport → crews → agents](docs/images/arch-system-placement.png)`
- [ ] 3.2 Insert `usage-flow.png` into `README.md` — at the start of the "### MCP Tools" section, immediately before the tools table, using: `![Usage flow: install → connect → launch → dispatch → pickup → nuke](docs/images/usage-flow.png)`
- [ ] 3.3 Insert `fleet-crew-hierarchy.png` into `docs/architecture.md` — immediately before the "## Components" heading, using: `![Fleet and crew hierarchy: Admiral → fleet → ghostship → crew → Captain → agents](docs/images/fleet-crew-hierarchy.png)`
- [ ] 3.4 Insert `sdd-workflow.png` into `docs/architecture.md` — immediately after the "## Ghost Academy" section's closing paragraph, using: `![SDD workflow: Spectre → Ghost → Banshee → Reaper, with Raven/Captain orchestration](docs/images/sdd-workflow.png)`
- [ ] 3.5 Insert `agent-roles-overview.png` into `docs/agents.md` — after the agents table and before the paragraph beginning "The five worker personas form the OpenSpec cycle...", using: `![Agent roles: the six personas and what each owns in the OpenSpec workflow](docs/images/agent-roles-overview.png)`

## 4. Tool Descriptions — transport/server.py

⚠️ **Skip this section — implement after TRN-71 (transport modularisation) has landed.** TRN-71 restructures `server.py` significantly; doing these edits mid-modularisation risks conflicts. The MCP tool registrations stay in `server.py` so these edits will be valid once TRN-71 is merged.

- [ ] 4.1 Update the server-level `description=` field in the `MCPServer(...)` constructor
- [ ] 4.2 Update `crews()` docstring — situational awareness framing
- [ ] 4.3 Update `launch()` docstring — Step 1 framing
- [ ] 4.4 Update `supply()` docstring — Step 2 framing
- [ ] 4.5 Update `dispatch()` docstring — Step 3 framing
- [ ] 4.6 Update `pickup()` docstring — Step 4 framing
- [ ] 4.7 Update `steer()` docstring — Step 4b framing
- [ ] 4.8 Update `evac()` docstring — Step 5 framing
- [ ] 4.9 Update `nuke()` docstring — Step 6 framing
- [ ] 4.10 Update `captain()` docstring — Autopilot framing

## 5. Plugin Skill Files

- [ ] 5.1 Revise `ghostship-admin/SKILL.md` — restructure the install section as an explicit numbered setup sequence: (1) install Podman prerequisites, (2) run `./install.sh`, (3) complete the `/login` auth flow (promote the "do this before your first launch" warning to a visible callout), (4) register the MCP client; add a clear handoff sentence at the end of step 4 pointing to `ghostship-command`
- [ ] 5.2 Revise `ghostship-command/SKILL.md` — add an explicit "Intended workflow order: launch → supply → dispatch → pickup/steer → evac → nuke" line to the mental model section before the per-step detail; surface the Captain autopilot path in the mental model overview; ensure the "Discover before assuming anything" block is clearly labeled as pre-work step 0

## 6. Verification

- [ ] 6.1 Confirm `IMAGE_PROMPTS.md` exists at `openspec/changes/trn-66-docs-infographics/IMAGE_PROMPTS.md` and contains ready-to-run prompts for all 5 images
- [ ] 6.2 Confirm all 5 image markdown references are inserted into the correct files (README.md, docs/architecture.md, docs/agents.md) — broken image links are expected until generation runs
- [ ] 6.3 Confirm `README.md` still passes a markdown lint check (no broken headings or table formatting from the insertions)
- [ ] 6.4 Confirm the two delta specs exist at `openspec/changes/trn-66-docs-infographics/specs/mcp-server/spec.md` and `openspec/changes/trn-66-docs-infographics/specs/agent-skill-contracts/spec.md`
- [ ] 6.5 Run `openspec status --change trn-66-docs-infographics` and confirm planning is complete

