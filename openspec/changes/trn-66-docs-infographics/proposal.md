## Why

Colleague demos revealed that ghostship's value and usage pattern aren't immediately apparent from the current README — the text explains it but a visual makes it click instantly. Two things specifically needed pictures: where ghostship sits relative to the wider AI toolchain, and the basic loop of how you actually use it day-to-day.

## What Changes

- Generate 2 infographics for the root README:
  - **Architecture diagram** — where ghostship fits: harness (Admiral) → ghostship MCP → transport → crew containers (KiroCrew) → agents; how it relates to Claude/Kiro/other harnesses
  - **Usage flow diagram** — the basic operational loop: install → connect → launch crew → dispatch task → pickup result → nuke when done
- Generate diagrams for `docs/` pages:
  - **Fleet/crew mental model** — Admiral, fleet, ghostship, crew, Captain, agents hierarchy
  - **SDD workflow** — Spectre → Ghost → Banshee → Reaper cycle with Captain/Raven orchestration
  - **Agent roles overview** — the six personas in one visual, showing what each owns in the workflow
- Integrate all images into README and relevant `docs/` pages with appropriate placement and captions
- All images generated via warp-image (ComfyUI), stored in `docs/images/`

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None — this is a documentation-only change with no spec-level behavior changes.

## Impact

- `docs/images/` — 5 new static image files
- `README.md` — 2 new diagrams inserted into appropriate sections
- `docs/architecture.md` — fleet/crew model and SDD workflow diagrams
- `docs/agents.md` — agent roles overview diagram
