## Why

The MCP Tools table in README.md lists 10 tools as text-only rows while the Agents table immediately above it has a recognisable ghost-cartoon image for each persona. Adding matching tool images gives each tool a memorable visual identity at a glance and makes the README visually consistent.

## What Changes

- Generate 10 ghost-cartoon images (one per MCP tool) via warp-image (ComfyUI on gpc), stored as `docs/images/tool-{name}.png`
- Add an image column to the MCP Tools table in `README.md`, matching the 64 px inline style used in the Agents table
- All images share the same ghost base silhouette as the existing agent images; props and background vary per tool to make each immediately recognisable even at 64 px thumbnail size

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None — this is a documentation and asset-only change. No spec-level behaviour changes.

## Impact

- `docs/images/` — 10 new static PNG files (`tool-crews.png`, `tool-launch.png`, `tool-supply.png`, `tool-evac.png`, `tool-nuke.png`, `tool-captain.png`, `tool-schedule.png`, `tool-dispatch.png`, `tool-steer.png`, `tool-pickup.png`)
- `README.md` — MCP Tools table gains an image column (first column, 64 px, matching Agents table)
