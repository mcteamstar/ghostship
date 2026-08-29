# Consumer-facing skills

Skill files for whoever is holding the MCP connection to `ghostship` — the
**Admiral**, driving the fleet from *outside* over `launch`/`dispatch`/
`pickup`/`steer`/`evac`/`supply`/`captain`/`schedule`/`nuke`/`crews`. Nothing
under here is ever copied into a crew container.

Three skills covering the three phases of ghostship operation:

- [`ghostship-admin`](ghostship-admin/SKILL.md) — install, connect a
  client, upgrade, tear down. Shell-driven, no MCP connection assumed. Start
  here if ghostship isn't installed yet.
- [`ghostship-capability`](ghostship-capability/SKILL.md) — configure what
  crews can do: agent personas, skills, steering, orders, MCP server
  catalogue, and crew compositions. Use after installation to customise the
  academy to your needs.
- [`ghostship-command`](ghostship-command/SKILL.md) — fleet operations once
  connected: launch, seed, dispatch, pickup/steer, Captain autopilot, evac,
  nuke. The Admiral's playbook for driving the fleet.

> **Not what you want if you're teaching a *dispatched* agent persona
> something** (ghost, spectre, banshee, wraith, reaper, raven — work that
> runs *inside* a crew). That's the separate in-container curriculum at
> [`academy/skills/`](../../academy/skills/INTERNAL_SKILLS.md), copied into
> every crew at `launch` per its `manifest.json`.
