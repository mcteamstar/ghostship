## 1. Style baseline check

- [ ] 1.1 Open `docs/images/agent-ghost.png` alongside a test generation to confirm the base prompt produces a matching ghost silhouette before running the full batch (see design.md §1 for the base prompt and §2 for the negative prompt)

## 2. Generate tool images — batch A (narrative/command tools)

- [ ] 2.1 Generate `docs/images/tool-crews.png` — admiral hat, clipboard, fleet silhouettes, dark navy background
- [ ] 2.2 Generate `docs/images/tool-captain.png` — captain's peaked cap, one arm extended pointing, scroll speech bubble, ship bridge background
- [ ] 2.3 Generate `docs/images/tool-steer.png` — gripping large ship's helm wheel with both arms, nautical chart/compass rose background
- [ ] 2.4 Generate `docs/images/tool-dispatch.png` — ghost curled inside cannon/pneumatic tube barrel angled, dark concrete silo background (must read as cylinder, not vertical launch)
- [ ] 2.5 Generate `docs/images/tool-pickup.png` — ghost squinting at oversized tablet with green checkmark, soft green mission-complete glow background

## 3. Generate tool images — batch B (lifecycle tools)

- [ ] 3.1 Generate `docs/images/tool-launch.png` — ghost rising from glowing circular floor portal, upward motion lines, deep space/star field background (must read as vertical motion from circle, not cannon)
- [ ] 3.2 Generate `docs/images/tool-supply.png` — ghost hugging oversized cargo crate with downward arrows on sides, amber-lit warehouse/docking bay background
- [ ] 3.3 Generate `docs/images/tool-evac.png` — ghost pulling glowing file folder upward out of vault door, red emergency lighting background
- [ ] 3.4 Generate `docs/images/tool-nuke.png` — ghost pressing T-shaped detonator plunger with both hands, orange-red explosion mushroom cloud background
- [ ] 3.5 Generate `docs/images/tool-schedule.png` — ghost holding large oversized pocket watch gripping the dial, teal/cyan starfield with faint calendar grid overlay background

## 4. Thumbnail review

- [ ] 4.1 View all 10 generated PNGs at 64 px width and confirm each prop silhouette is readable (dominant prop occupies >40% of frame per design.md §3)
- [ ] 4.2 Confirm `tool-dispatch.png` and `tool-launch.png` are visually distinct at 64 px — re-run either if they could be confused (see design.md §3 disambiguation rule)
- [ ] 4.3 Re-run any image that fails the 64 px readability or style-consistency check, adding `oversized` to the prop description and/or simplifying the background

## 5. README.md integration

- [ ] 5.1 Update the MCP Tools table header in `README.md` to add a blank image column first: `|  | Tool | Description |` with separator `|:-|:-----|:------------|`
- [ ] 5.2 Prefix each of the 10 tool rows with `| <img src="docs/images/tool-{name}.png" width="64"> |` matching the exact pattern used in the Agents table
