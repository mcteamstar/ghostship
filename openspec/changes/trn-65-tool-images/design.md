## Context

See proposal.md — Why for motivation.

The six agent images (`docs/images/agent-*.png`) were generated via warp-image (ComfyUI on gpc) and share a consistent ghost-cartoon style: flat cartoon ghost silhouette, white body, expressive black eyes, styled props, and a thematic background. These 10 tool images must read as members of the same visual family.

The MCP Tools table in README.md currently has two columns (`Tool`, `Description`). The Agents table immediately above it uses `| <img src="..." width="64"> | **Name** | Description |` — the same pattern will be applied to the tools table.

## Goals / Non-Goals

**Goals:**

- 10 PNG images stored as `docs/images/tool-{name}.png`, visually consistent with the existing agent images
- Each image has props/background readable at 64 px (the rendered thumbnail size in README.md)
- `dispatch` and `launch` are visually distinct at thumbnail size
- README.md MCP Tools table updated to include an image column matching the Agents table layout

**Non-Goals:**

- Animated GIFs or any format other than static PNG
- Generating or changing the agent images
- Any doc changes beyond the README.md MCP Tools table
- Any code changes

## Decisions

### 1. Shared base prompt strategy

**Decision:** Use a single locked base prompt that defines the ghost silhouette and art direction; vary only the prop description and background per tool.

**Rationale:** The agent images look cohesive because they share a silhouette baseline. Drifting even one adjective (e.g. "ethereal" vs "cartoon") across prompts produces visible style inconsistency at thumbnail scale. One base prompt with a per-tool suffix is the lowest-risk approach.

**Base prompt (locked across all 10 runs):**

```
flat cartoon ghost, white rounded body silhouette, large expressive dot eyes,
simple friendly face, clean linework, single ghost character, centered composition,
square format, solid or simple patterned background, no text, no labels,
digital illustration style consistent with existing ghostship agent art
```

**Alternative considered:** Per-tool full prompt from scratch — rejected because prop/background wording variation bleeds into silhouette variation (different body widths, transparency treatment) across ComfyUI seeds.

### 2. Negative prompt (shared)

Applied to all 10 runs to prevent drift from the agent-image family:

```
photorealistic, 3d render, multiple ghosts, text, watermark, blurry,
low quality, human face, skeleton, scary, horror, grim reaper, detailed texture,
complex background, busy background
```

### 3. Per-tool prompt variations

Each entry extends the base prompt with a `PROP:` and `BACKGROUND:` suffix. Props are chosen to be readable as a silhouette at 64 px — avoid fine detail (e.g. "text on clipboard" won't read; "oversized clipboard shape" will).

| Tool | PROP | BACKGROUND |
|------|------|-----------|
| `crews` | admiral hat on ghost's head, holding clipboard, small fleet silhouettes in background | dark navy blue, faint ship silhouettes horizon line |
| `launch` | ghost rising up from glowing circular launch pad portal beneath feet, upward motion lines | deep space black, subtle star field, glowing teal portal glow |
| `supply` | ghost hugging/carrying oversized cargo crate with downward-pointing arrows on its sides | warehouse interior, warm amber industrial lighting, docking bay shelves |
| `evac` | ghost pulling a glowing file folder upward out of a vault door, folder trails upward arrows | red emergency lighting, dark vault interior, dramatic red glow |
| `nuke` | ghost pressing both hands down on large T-shaped detonator plunger | dramatic orange-red explosion mushroom cloud background |
| `captain` | captain's peaked cap on ghost's head, one arm extended pointing outward, scroll speech bubble beside it | ship bridge interior, nautical instruments, warm gold tones |
| `schedule` | ghost holding large oversized pocket watch, one hand gripping the dial | teal/cyan starfield with faint calendar grid overlay |
| `dispatch` | ghost curled small inside a large cannon/pneumatic tube barrel, cannon aimed at angle | dark concrete silo interior, single spotlight on the cannon |
| `steer` | ghost gripping a large ship's wooden helm wheel with both arms | nautical chart background, compass rose, ocean map lines |
| `pickup` | ghost holding large tablet/clipboard at arm's length and squinting at it, green checkmark visible on screen | soft green mission-complete glow, minimal background |

**dispatch vs launch disambiguation at thumbnail:** `dispatch` = ghost curled *inside* a cannon (contained, cylindrical prop dominant), `launch` = ghost *rising from* a circular floor portal with upward lines (vertical motion). The dominant shape differs: cylinder vs circle with upward arrow. Verified readable at 64 px by checking that the dominant prop silhouette occupies >40% of the frame.

### 4. Image dimensions and warp-image settings

- **Output size:** 512×512 px (warp-image/ComfyUI default square); PNG
- **Stored as-is:** no post-processing resize needed — GitHub markdown renders `width="64"` client-side
- **Seed:** let warp-image pick; note the seed used per image in tasks.md completion notes for reproducibility

### 5. README.md integration

The MCP Tools table header changes from:

```markdown
| Tool | Description |
|:-----|:------------|
```

to:

```markdown
|  | Tool | Description |
|:-|:-----|:------------|
```

Each row prefixed with `| <img src="docs/images/tool-{name}.png" width="64"> |` — matching the exact `width="64"` and relative-path pattern used in the Agents table.

## Risks / Trade-offs

- **Style drift between agent images and tool images** → Mitigation: use identical base prompt adjectives (`flat cartoon ghost, white rounded body silhouette`) and apply negative prompt consistently; review first 2–3 images against `agent-ghost.png` before running the full batch.
- **Props unreadable at 64 px** → Mitigation: props are chosen for silhouette size (pocket watch, cannon, helm wheel are all large geometric shapes). If any prop is unreadable after generation, re-run with `oversized` reinforced and more negative-space background.
- **dispatch/launch confusion** → Mitigation: explicit dominant-shape rule above (§3). If both look like "ghost going up," adjust dispatch to have ghost *inside* cannon with cannon barrel clearly horizontal or angled, not vertical.
- **warp-image/ComfyUI unavailability on gpc** → Mitigation: images are independent; partial batches can be committed. README.md update is the final task and only runs once all 10 images exist.

## Open Questions

None — all decisions needed to proceed are resolved above.
