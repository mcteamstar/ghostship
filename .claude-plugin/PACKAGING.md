# Dual-format plugin packaging

This directory serves double duty as two different plugin packages at once,
sharing one `skills/` directory:

- An [Agent Plugins](https://agent-plugins.org/) v1.0.0 package — the open,
  vendor-neutral format that Kiro Powers builds on. Manifest: `plugin.json`.
  MCP config: `mcp.json`.
- A native Claude Code plugin. Manifest: `.claude-plugin/plugin.json`
  (nested one level deeper, per Claude Code's convention that the manifest
  lives in a `.claude-plugin/` subfolder of the plugin root). MCP config:
  `.mcp.json` (dot-prefixed, at plugin root).

The two manifests carry identical metadata; they're duplicated rather than
shared because each spec wants the file at a different path. The repo-root
[`marketplace.json`](marketplace.json) points Claude Code at this same
directory (`"source": "./.claude-plugin"`), so both formats resolve against
one shared `skills/` tree with no divergent content. See
[`skills/EXTERNAL_SKILLS.md`](skills/EXTERNAL_SKILLS.md) for what the skill
itself teaches.

## Installing the Claude Code plugin

```bash
claude plugin marketplace add mcteamstar/ghostship
claude plugin install ghostship@ghostship
```

**If you already added `ghostship` to `mcpServers` by hand** (per the
README's manual Claude Code instructions, or via `ghostship-admin`'s
"Connect a client" step), installing the plugin adds a *second*,
separately-namespaced MCP connection to the same endpoint rather than
replacing or merging with the first — Claude Code does not deduplicate
same-named servers across a plugin and a standalone config. Pick one path:
either keep the manual `mcpServers` entry and skip the plugin, or use the
plugin and remove the manual entry.

## VS Code (native Agent Plugins)

VS Code's own [Agent Plugins](https://code.visualstudio.com/docs/agent-customization/agent-plugins)
support (GitHub Copilot Chat) auto-detects three manifest formats when it
loads a plugin directory: a root `plugin.json` declaring the Agent Plugins
`$schema` (Agent Plugins format), a root `plugin.json` with no such
`$schema` (Copilot format), or `.claude-plugin/plugin.json` (Claude
format) — checked in that order.

This repo's root has `.claude-plugin/plugin.json` (our Agent Plugins
manifest, since it declares the `$schema`), so VS Code should detect it as
Claude format and treat the repo root as the plugin root. That's a
mismatch: this package's actual `.mcp.json` and `skills/` live one level
deeper, inside `.claude-plugin/` itself (that directory is the plugin root
for Claude Code, not the repo root — see above). VS Code may register the
plugin but find no MCP config or skills at the repo-root paths it expects.
This hasn't been tested end-to-end; treat it as a known risk, not a
confirmed bug.

**"Install Plugin From Source"** (Command Palette or the Agent
Customizations editor) takes a bare Git repository URL — no documented way
to pin a branch/ref or point at a subdirectory. It clones whatever the
default branch is and scans from the true repo root, so it can't target
this package specifically on a non-default branch.

Until that's sorted out, the reliable path is a local clone plus the
`chat.pluginLocations` setting, pointed directly at `.claude-plugin` so
VS Code treats that directory (not the repo root) as the plugin root:

```json
"chat.pluginLocations": {
  "/path/to/ghostship/.claude-plugin": true
}
```

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
