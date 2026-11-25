# Tasks

**Plane ticket:** TRN-369

## 1. Wire Playwright into spec-ops

- [x] 1.1 Add `playwright` to `crews/spec-ops/manifest.json` and add `@playwright` to Ghost's `tools` and `allowedTools`; leave the other personas unchanged.
- [x] 1.2 Ensure Academy stages the name-keyed MCP map, explicitly runs setup for the selected ACP backend, and copies each selected server into only the persona specs whose `tools` grant references it, preserving explicit persona entries.

## 2. Verify the real fresh-crew launch path

- [x] 2.1 Launch a fresh Corsair `spec-ops` crew and verify its native harness MCP config and Ghost tool grant. Verified Ghost's grants and namespaced MCP tools in `trn-369-playwright-check7`.
- [x] 2.2 Use the configured Playwright MCP as `kirocrew` to open a local `data:` page and verify its title/body. Record whether any failure is MCP package resolution, MCP startup, browser resolution, or browser launch; do not treat shell `PATH` or module probes as equivalent evidence. The initial configured browser launch failed at Chromium sandbox initialization; after adding headless `--no-sandbox`, the fresh crew returned title `TRN-369-smoke` and heading `local-page-ok`.

## 3. Ensure Chromium is available in the image

- [x] 3.1 If the fresh-crew smoke check finds no compatible browser or cannot access it, add the matching Chromium revision and required libraries to the spec-ops image at a stable path outside `/home/kirocrew`; configure the runtime path and pin the MCP version only if needed for compatibility. If the existing image already passes, record this task as not needed. The image now installs Debian Chromium at `/usr/bin/chromium`; the catalogue points Playwright MCP to it with downloads disabled.
- [x] 3.2 Add a fresh-image integration smoke check for the configured Playwright launch as `kirocrew`, with browser downloads unavailable and normal container restrictions; wire it into `.github/workflows/test.yml` and verify it passes. Passed against the built ARM64 image with `no-new-privileges`, `SYS_ADMIN` and `NET_RAW` dropped, and an empty browser cache.
- [x] 3.3 Build and run the smoke check on each supported crew image architecture; verify browser launch does not require a first-use browser download. The ARM64 smoke check passed locally. The native x86_64 Carrier crew returned title `TRN-369-x86-smoke` and heading `x86-page-ok` with the browser cache empty and Chromium supplied by the image.

## 4. Document the composition and image behavior

- [x] 4.1 Document how `spec-ops` selects Playwright, how Ghost receives its tool grant, the browser-resolution check, and how to refresh the Academy snapshot and rebuild the image if Chromium changes.
- [x] 4.2 Verify documentation matches the manifest, persona grants, catalogue entry, and image behavior established by the fresh-crew smoke test.
