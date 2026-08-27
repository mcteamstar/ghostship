# Agent Plugins packaging

This directory is an [Agent Plugins](https://agent-plugins.org/) v1.0.0
package — `plugin.json` + `skills/` (+ optional `mcp.json`), the open,
vendor-neutral format that Kiro Powers now build on. See
[`skills/EXTERNAL_SKILLS.md`](skills/EXTERNAL_SKILLS.md) for what the skill
itself teaches.

**Not yet consumed by Claude Code.** As of this writing, Claude Code reads
standalone `SKILL.md` files but does not implement `plugin.json`/`mcp.json`
at all — this package targets other Agent-Plugins-compatible clients (Kiro
Powers, and whatever else lands support). Keeping it here costs nothing
regardless: the skill content is identical either way, this is just the
portable wrapper around it.

## `mcp.json` covers the unauthenticated local default only

`mcp.json` declares `http://localhost:64057/mcp` — ghostship's default,
unauthenticated, loopback endpoint. That's the only case the spec lets a
package express. It does **not** cover:

- **Remote deployments** — Agent Plugins v1.0.0 requires HTTPS for any
  non-loopback URL; a plain-`http://` remote address isn't conformant.
- **API-key deployments** — the spec forbids embedding secrets in
  `headers`/`env`, and forbids environment-variable or placeholder
  expansion there too. Even `${GHOSTSHIP_API_KEY}`-style syntax — the form
  `ghostship-admin`'s own native client config uses — isn't a legal
  workaround: a client would ship that literally, as a meaningless string,
  rather than resolving it.

Anyone running a keyed or remote ghostship install still needs to configure
that connection manually — see
[`skills/ghostship-admin/SKILL.md`](skills/ghostship-admin/SKILL.md)
("Connect a client"), which stays inside this package rather than
depending on the wider repository. This package doesn't and can't replace
that step.

## What this package doesn't do

It's a connection descriptor, not an installer. It assumes ghostship is
already running. It does not install Podman, build crew images, run
`./install.sh`, or complete kiro-cli device auth — see
[`skills/ghostship-admin/SKILL.md`](skills/ghostship-admin/SKILL.md) for
all of that.
