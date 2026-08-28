## Context

TRN-61 investigated Kiro Powers vs Agent Plugins vs workspace skills for distributing the Ghostship operator skill. Research (crew `trn-61-investigation`, three parallel Wraith agents) concluded:

- Powers and workspace skills are complementary: workspace skills are the right primitive for in-crew operation (fully headless, version-controlled, no install step); Agent Plugins 1.0 is the right standard for external distribution.
- The consumer skill needs a split: `ghostship-admin` for the install/auth/setup side (shell-driven, pre-MCP) and `ghostship-command` for fleet operation over MCP (minimal footprint, no install content).
- `mcp.json` is worth including but has meaningful constraints that must be documented explicitly (loopback-only, no secrets, limited to unauthenticated default).

## Goals / Non-Goals

**Goals:**
- Package the consumer-facing skills as a conformant Agent Plugins v1.0.0 package (`plugin.json` + `mcp.json` + `skills/`).
- Split into `ghostship-admin` (pre-MCP, shell-driven) and `ghostship-command` (post-connection, fleet operation) to keep each skill's context footprint tight.
- Document the `mcp.json` constraints clearly so consumers aren't surprised.
- Disambiguate the two skill trees: external (`plugin/skills/`) vs internal (`academy/skills/`).

**Non-Goals:**
- Any transport (`server.py`) changes.
- Any crew image changes.
- Claude Code Agent Plugins support (not yet implemented upstream — this packages for clients that do support it; Claude Code users still symlink/copy the skill files).
- Supporting keyed or remote installs via `mcp.json` (spec forbids this; `ghostship-admin` documents the manual path instead).

## Decisions

**Agent Plugins 1.0 over a standalone SKILL.md:** The spec is the distribution standard to align with. Adding `plugin.json` + `mcp.json` costs nothing — the skill content is identical either way, the package is just the portable wrapper. Clients that don't support the spec yet (Claude Code) can ignore it; clients that do get a one-directory install.

**Split into `ghostship-admin` + `ghostship-command`:** A single combined skill bloats the context window of sessions that only ever drive an already-running fleet — they load all the install/auth content they'll never use. The natural boundary is whether an MCP connection to `ghostship` already exists: `ghostship-admin` is everything needed before that connection; `ghostship-command` is everything after.

**`mcp.json` covers loopback-only, unauthenticated default:** Agent Plugins 1.0 requires HTTPS for non-loopback URLs and forbids secrets in `headers`/`env` (even `${GHOSTSHIP_API_KEY}`-style env expansion is not a legal workaround). The only conformant entry is `http://localhost:64057/mcp`. `PACKAGING.md` documents this limitation and points to `ghostship-admin` for the manual configuration path.

**`academy/skills/` cross-link:** Without it, anyone landing in `academy/skills/` while looking for the Admiral-side skill has no pointer. `INTERNAL_SKILLS.md` at the academy root clarifies the distinction and links to `plugin/skills/EXTERNAL_SKILLS.md`.

## File Layout

```
plugin/
  plugin.json                   # Agent Plugins 1.0 manifest
  mcp.json                      # MCP server declaration (loopback, unauthenticated)
  PACKAGING.md                  # mcp.json constraints, what this package does/doesn't do
  skills/
    EXTERNAL_SKILLS.md          # index + disambiguation (external vs internal)
    ghostship-admin/
      SKILL.md                  # install, auth, connect, upgrade, uninstall
    ghostship-command/
      SKILL.md                  # fleet operation over MCP

academy/skills/
  INTERNAL_SKILLS.md            # in-container curriculum index + cross-link to plugin/skills/
  .gitkeep                      # ensures the directory is tracked even when empty
```
