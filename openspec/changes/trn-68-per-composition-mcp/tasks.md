## 1. install.sh — add academy/mcp/ to copy step and compose.yml

- [x] 1.1 In `install.sh`, add `academy/mcp` to the rsync copy step (alongside `agents`, `skills`, etc.) so `${DATA_DIR}/academy/mcp/` is populated at install time; add the corresponding `cp -r` fallback line
- [x] 1.2 Create `academy/mcp/` in the repo with a `README.md` documenting the catalogue convention (file naming, JSON format, `${VAR}` substitution, how to wire a server into a manifest)
- [x] 1.3 Add `academy/mcp/playwright.json` to the catalogue — stdio entry using `npx @playwright/mcp@latest`; not declared in any manifest by default
- [x] 1.4 In the `compose.yml` heredoc in `install.sh`, add `- ${DATA_DIR}/academy/mcp:/mcp:ro` as a new volume entry alongside the existing academy mounts
- [x] 1.5 Add a log line confirming the mcp copy (`echo "✓ academy/mcp/ copied to ${DATA_DIR}"`)
## 2. transport/server.py — write mcp.json from composition manifest

- [x] 2.1 In `_copy_agents()`, read the composition manifest's `mcpServers` array (if present); if absent or empty, skip `mcp.json` creation
- [x] 2.2 For each server name in `manifest.mcpServers`, resolve it against `/mcp/<name>.json`; log a warning and skip if the file is absent
- [x] 2.3 Substitute `${VAR}` references in resolved catalogue entries using the transport's `os.environ`; log a warning for any unset variable but continue
- [x] 2.4 For any resolved entry containing a `headers` field, set `poolable: false` automatically
- [x] 2.5 Write the resolved entries as `~/.kiro/mcp.json` inside the crew container via `container_archive_put`, using the same tar pattern as agent JSON copying
- [x] 2.6 Log the server names written to `mcp.json` (matching the pattern used for agent and skill copy logging)

## 3. Unit tests

- [x] 3.1 Test: manifest with `mcpServers` → correct `mcp.json` written with resolved entries
- [x] 3.2 Test: manifest with no `mcpServers` key → no `mcp.json` written
- [x] 3.3 Test: manifest references unknown server name → warning logged, other servers written, no exception
- [x] 3.4 Test: catalogue entry with `headers` → `poolable: false` added automatically
- [x] 3.5 Test: catalogue entry with `${VAR}` → substituted when env var is set
- [x] 3.6 Test: catalogue entry with `${MISSING}` → warning logged, literal string written, setup continues
- [x] 3.7 Run full unit suite and confirm all tests pass

## 4. Documentation

- [x] 4.1 In `docs/configuration.md`, add a section documenting the MCP server catalogue format, the `manifest.json → mcpServers` array, and the `${VAR}` substitution pattern for secrets
- [x] 4.2 Update `docs/configuration.md` with the full `playwright.json` entry as a worked example showing the stdio format alongside the HTTP format

## 5. Integration validation (requires live podman host)

- [ ] 5.1 Add a test server entry to `academy/mcp/`, reinstall, and confirm `DATA_DIR/academy/mcp/` is populated
- [ ] 5.2 Add `mcpServers` to `crews/spec-ops/manifest.json`, launch a crew, and confirm `~/.kiro/mcp.json` exists inside the container with the correct entries
- [ ] 5.3 Confirm a `${VAR}` reference in a catalogue entry is substituted correctly in the written `mcp.json`
- [ ] 5.4 Remove the test entries and restore `manifest.json` to its original state
