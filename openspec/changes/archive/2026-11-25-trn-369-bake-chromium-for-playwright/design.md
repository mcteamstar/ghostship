# Design

## Context

The Playwright server is already catalogued at `academy/mcp/playwright.json` and currently runs through `npx @playwright/mcp@latest`. Academy only stages catalogue entries named in a crew's `manifest.json`; `spec-ops` previously had `"mcpServers": []`. Agents also need `@<server>` in their tool grants, and Ghost had no `@playwright` grant.

The fresh-crew checks exposed several separate gaps. Academy staging originally wrote `servers.json` as a list, but `.agents/setup` expects a name-keyed object. Native Codex config alone also did not provide the server in the Codex session: KiroCrew builds `session/new` MCP entries from the selected persona's `mcpServers`. After fixing both paths and granting Ghost the tool, a fresh Corsair Codex session exposed the namespaced Playwright tools. Its configured MCP then found Debian Chromium but Chromium failed to start with `No usable sandbox!` inside the existing crew/Codex sandbox. A static run in the same image with normal container restrictions had already launched it; disabling Chromium's nested sandbox is the final launch adjustment. The initial filesystem probe missed `/home/kirocrew/.cache/ms-playwright` and did not launch the configured MCP, so it was not evidence that Chromium was absent.

## Goals / Non-Goals

**Goals:**

- Make the existing Playwright MCP available in fresh `spec-ops` crews and grant its tools to Ghost.
- Verify the normal Academy staging and harness setup, then launch headless Chromium through the MCP as `kirocrew` and read a local page.
- Ensure the browser resolved by the MCP is present and usable in a fresh image without a first-use browser download. Provision or relocate it in the image only if the end-to-end check shows that is necessary.
- Keep image browser files available when `/home/kirocrew` is mounted as a crew volume.

**Non-Goals:**

- Enable Playwright in every crew composition or grant it to every persona.
- Add Firefox, WebKit, headed browsing, or remote browser support.
- Bake the Node MCP package into the image unless the real MCP startup demonstrates that the current catalogue command is unsuitable.

## Decisions

### Wire Playwright through Academy composition

Set `mcpServers` to `["playwright"]` in `crews/spec-ops/manifest.json`. Add `@playwright` to Ghost's `tools` and `allowedTools` lists, leaving other personas unchanged. Academy resolves the existing catalogue entry and stages `.agents/mcp/servers.json` as an object keyed by server name; this is the shape consumed by `.agents/setup` when it merges the shared catalogue into native config. When Academy copies personas, it also adds each selected server to `mcpServers` only on personas whose `tools` grant references that server. An explicit persona-level entry wins over the composition entry. KiroCrew uses this persona spec to assemble the session MCP array for Codex, and Kiro CLI reads the same per-agent configuration natively.

`AcademyLoader` runs `.agents/setup --yolo`, which only configures harnesses whose executables are on `PATH`. The selected ACP backend can be present even when its standalone CLI is not. Run `.agents/setup <selected-backend> --yolo` explicitly as well as the existing all-detected setup so the active backend receives its native config. That setup is supplementary: in Codex crews the per-agent entry is what KiroCrew projects into the session's `mcpServers` array. Keep `academy/mcp/playwright.json` on its current `npx` command unless the end-to-end launch reveals a concrete need to change it.

This scopes browser access to the spec-ops crew and its general-purpose Ghost persona while exercising the established composition mechanism.

### Diagnose the browser through the configured MCP

Launch a fresh Corsair `spec-ops` crew after composition setup. First verify the harness-native MCP configuration and that Ghost receives the `@playwright` tool. Then use that tool to navigate to a local `data:` page and read its title/body. Capture whether a failure occurs while resolving the MCP package, starting the MCP, resolving Chromium, or launching Chromium. Do not use shell `PATH` checks as a substitute for this execution path.

The fresh crew proved that the existing image had no browser at Playwright's default Chrome path (`/opt/google/chrome/chrome`), and adding the Debian Chromium package plus `--executable-path /usr/bin/chromium` resolved browser discovery. The next launch reached that executable but failed because Chromium's nested sandbox could not initialize in the existing Codex/crew sandbox. Run Chromium headlessly with Playwright MCP's `--no-sandbox` option; this disables only the nested Chromium sandbox, while the outer crew container restrictions remain enabled. Keep browser downloads disabled and repeat the local-page test through the real MCP session. This passed on the local ARM64 image. The x86_64 image builds under emulation on the ARM64 development host, but the emulated CPU does not provide SSE3, which Debian Chromium requires; the existing Podman integration job exercises the same smoke test on a native x86_64 GitHub runner.

### Test the normal crew runtime

Use the built spec-ops image and its normal runtime user and container restrictions. Check that the mounted crew home does not mask browser files. The smoke page should be local, so the browser test does not depend on an external website. Preserve the outer container security settings; Chromium's internal sandbox is disabled because it cannot start inside this nested environment.

## Risks / Trade-offs

- **`@latest` MCP behavior can change** → Keep the first change focused on verified composition wiring; pin the MCP and its browser revision if the fresh-crew test demonstrates that stability requires it.
- **Image growth if Chromium is missing** → Add only the compatible Chromium browser and required libraries, in the spec-ops image rather than a shared image.
- **A browser under the crew home may be hidden by its volume** → Exercise a fresh crew with the normal home mount; if provisioning is needed, use an image-owned path.
- **Existing crews do not receive composition or image changes** → Replace/relaunch crews from the updated Academy snapshot and image. Refresh the transport's Academy data snapshot with the documented install process.

## Migration Plan

Update the Academy composition files and refresh the transport's Academy snapshot using the normal install process. Rebuild the spec-ops image only if Chromium must be provisioned or relocated. Launch a fresh Corsair crew and run the end-to-end MCP smoke check. Existing crews retain their prior composition and image until replaced. Roll back by reverting the composition/persona changes and any conditional image/catalogue changes, then refresh the snapshot and rebuild as applicable.
