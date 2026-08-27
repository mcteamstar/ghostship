# Consumer-facing skills

Skill files for whoever is holding the MCP connection to `ghostship` — the
**Admiral**, driving the fleet from *outside* over `launch`/`dispatch`/
`pickup`/`steer`/`evac`/`supply`/`captain`/`schedule`/`nuke`/`crews`. Nothing
under here is ever copied into a crew container.

Two skills, split by whether an MCP connection to `ghostship` already
exists:

- [`ghostship-admin`](ghostship-admin/SKILL.md) — install, connect a
  client, upgrade, tear down. Shell-driven, no MCP connection assumed.
- [`ghostship-command`](ghostship-command/SKILL.md) — the fleet lifecycle
  itself once connected: launch, dispatch, pickup/steer, Captain, nuke.

> **Not what you want if you're teaching a *dispatched* agent persona
> something** (ghost, spectre, banshee, wraith, reaper, raven — work that
> runs *inside* a crew). That's the separate in-container curriculum at
> [`academy/skills/`](../../academy/skills/INTERNAL_SKILLS.md), copied into
> every crew at `launch` per its `manifest.json`.
