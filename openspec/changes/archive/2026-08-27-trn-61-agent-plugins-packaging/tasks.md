## 1. Package structure

- [x] 1.1 Create `plugin/` directory with `plugin.json` (Agent Plugins 1.0 manifest: name, version, description, repository, license, keywords).
- [x] 1.2 Create `plugin/mcp.json` with the `ghostship` MCP server entry pointing at `http://localhost:64057/mcp` (streamable-http, loopback default only).
- [x] 1.3 Create `plugin/PACKAGING.md` documenting the `mcp.json` constraints (loopback-only, no secrets, no remote http://) and what the package does/doesn't do.

## 2. External skills

- [x] 2.1 Create `plugin/skills/EXTERNAL_SKILLS.md` indexing the two skills and disambiguating external (`plugin/skills/`) vs internal (`academy/skills/`) curricula.
- [x] 2.2 Create `plugin/skills/ghostship-admin/SKILL.md` covering: prerequisites, `./install.sh`, the `/login`–`/logout` auth flow (state machine, guards, first-time sequence), endpoint API-key setup (`--api-key`), connecting a client (kiro-cli, Claude Code), plumbing skill files into an agent, `./start.sh`, upgrade/rebuild table, `./uninstall.sh`, pointer to live docs.
- [x] 2.3 Create `plugin/skills/ghostship-command/SKILL.md` covering: mental model (fleet/crew/task/composition), discover-before-assuming (resources), full core lifecycle (launch/supply/dispatch/pickup/steer/evac/nuke), schedule, Captain autopilot (sdd template, interval guidance), mail (how to surface it without reaching into mailboxes), guardrails, pitfalls table, worked examples (manual relay and autopilot).

## 3. Internal skills index

- [x] 3.1 Create `academy/skills/INTERNAL_SKILLS.md` explaining the in-container curriculum scope and cross-linking to `plugin/skills/EXTERNAL_SKILLS.md`.
- [x] 3.2 Add `academy/skills/.gitkeep` so the directory is tracked when empty.

## 4. Verification

- [x] 4.1 Confirm `plugin.json` validates against the Agent Plugins 1.0 `$schema` URI (manual check against spec at agent-plugins.org).
- [x] 4.2 Confirm `mcp.json` is a valid Agent Plugins 1.0 MCP descriptor (loopback URL, no secrets, `streamable-http` type).
- [x] 4.3 Confirm both `SKILL.md` frontmatter blocks are well-formed (name, description, metadata.author, metadata.version).
- [x] 4.4 Confirm cross-links between `EXTERNAL_SKILLS.md`, `INTERNAL_SKILLS.md`, and `PACKAGING.md` are correct relative paths.
