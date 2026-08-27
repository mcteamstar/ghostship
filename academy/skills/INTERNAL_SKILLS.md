# Ghost Academy skills

Skill files for the KiroCrew agent personas (`ghost`, `spectre`, `banshee`,
`wraith`, `reaper`, `raven`) that run **inside** every crew container. Each
subdirectory here is a `SKILL.md` copied into a crew's `~/.kiro/skills/` at
`launch`, filtered against the crew type's `manifest.json` (see
[docs/architecture.md](../../docs/architecture.md#ghost-academy)).

Adding a skill here means teaching a dispatched agent something — e.g. how
to send inter-agent mail (`ghostship-mail`) or drive the OpenSpec lifecycle
(`openspec-*`).

> **Not what you want if you're teaching an *external* agent how to drive
> ghostship itself over MCP** (launch/dispatch/pickup/steer/evac/nuke, the
> Admiral's side). That skill lives at
> [`plugin/skills/`](../../plugin/skills/EXTERNAL_SKILLS.md) instead — it's
> never copied into a crew, it's for whoever is holding the MCP connection.
