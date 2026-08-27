## Why

TRN-61 investigated whether to adopt Kiro Powers (Agent Plugins 1.0 format) for distributing Ghostship's operator skill, and how to structure the consumer-facing skill. The research confirmed:

- Kiro Powers are built on the open **Agent Plugins 1.0 spec** (backed by Amazon, Cursor, Microsoft, OpenAI, Vercel at agent-plugins.org). The format is `plugin.json` + `skills/` + optional `mcp.json`.
- For distributing a persona bundle externally, Agent Plugins is the right packaging standard to align with.
- The single existing consumer skill covered too much ground — install, auth, and fleet operation were mixed together, causing context bloat in sessions that only ever drive an already-running fleet.

This change implements the conclusions of that research: package the consumer-facing skill as an Agent Plugins v1.0.0 package, and split it into two purpose-scoped skills (`ghostship-admin` and `ghostship-command`).

## What Changes

- **`plugin/` directory** — new Agent Plugins v1.0.0 package at the repo root: `plugin.json`, `mcp.json`, `PACKAGING.md`, and `skills/`.
- **`plugin/skills/ghostship-admin/SKILL.md`** — install, the `/login`–`/logout` auth flow, endpoint API-key setup, connecting a client, plumbing skill files into an agent, `start.sh`, upgrade, uninstall. Shell-driven, no MCP connection assumed.
- **`plugin/skills/ghostship-command/SKILL.md`** — fleet operation once connected: launch, supply/evac, dispatch (all six personas), pickup/steer, captain autopilot, schedule, nuke. Minimal context footprint; no install or auth content.
- **`plugin/skills/EXTERNAL_SKILLS.md`** — cross-links the two skills and disambiguates the external (`plugin/skills/`) vs internal (`academy/skills/`) curricula.
- **`academy/skills/INTERNAL_SKILLS.md`** — the mirror cross-link: explains that `academy/skills/` is the in-container curriculum for dispatched agent personas, not for the external Admiral.
- **`mcp.json` scope** — covers the unauthenticated local default (`http://localhost:64057/mcp`) only. Agent Plugins 1.0 forbids embedding secrets in `headers`/`env` and forbids non-loopback `http://` URLs, so keyed and remote installs must configure their connection manually via `ghostship-admin`.
- **Guardrail in `ghostship-command`** — explicit warning and pitfalls-table entry for the real failure mode of dispatching into an unseeded crew workspace.

## Capabilities

### New Capabilities

None. This change adds packaging and documentation only — no transport code changes.

### Modified Capabilities

None changed. The `plugin/` directory is additive; existing skills and academy content are not replaced.

## Impact

- External clients that support Agent Plugins 1.0 (Kiro Powers, others as they land support) can install the `plugin/` directory as a single package to get both skills and the local MCP connection.
- Existing consumers of a standalone `SKILL.md` are unaffected — the skill files live inside `plugin/skills/` and can be symlinked or copied as before.
- No changes to `transport/server.py` or any crew image content.
