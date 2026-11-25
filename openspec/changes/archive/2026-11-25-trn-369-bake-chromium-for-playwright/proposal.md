# Proposal

## Why

The Corsair smoke run did not establish that Chromium is missing. It found no Playwright tools because `spec-ops` declared no MCP servers and Ghost lacked the `@playwright` grant. After wiring those and fixing the name-keyed config expected by `.agents/setup`, a fresh Codex crew still had no Playwright tools. KiroCrew builds Codex's session MCP array from the selected persona's `mcpServers`; installing a server into native Codex config alone does not put it in that per-session array. The probe also missed the crew user's actual browser cache path. Fix Academy's persona MCP projection and test a real fresh-crew launch before deciding whether Chromium needs image changes.

## What Changes

- Select the existing Playwright MCP catalogue entry in the `spec-ops` composition and grant its tools to Ghost, the general-purpose implementation persona.
- Serialize Academy's staged MCP server config in the shape consumed by `.agents/setup`, and copy each composition-selected server into the `mcpServers` block of only the personas whose `tools` reference it. Preserve persona-specific entries.
- Keep the selected ACP backend setup explicit; do not rely on the native Codex config as a substitute for the KiroCrew session MCP array.
- Add a fresh Corsair crew smoke check that verifies the staged MCP configuration and uses Playwright to open a local page as `kirocrew`.
- Confirm which browser path the MCP actually resolves. If the fresh image lacks a compatible browser or cannot access it, provision the matching Chromium and required system libraries in the image, outside the mounted crew home, and verify no browser download is needed at first use.
- Document the composition wiring, the browser availability check, and the image rebuild needed if browser contents change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `installation/crew-images`: a fresh `spec-ops` crew exposes Playwright to Ghost and can launch a compatible local Chromium browser as `kirocrew`.

## Impact

`crews/spec-ops/manifest.json`, `academy/agents/ghost.json`, the existing `academy/mcp/playwright.json` entry if its command needs adjustment, `crews/spec-ops/Containerfile` only if Chromium must be provisioned, Academy and image integration coverage, and crew image documentation. The initial Corsair probe is treated as inconclusive about browser availability; the end-to-end launch determines whether an image change is needed.
