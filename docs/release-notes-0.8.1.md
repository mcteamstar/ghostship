# Ghostship v0.8.1 Release Notes

## Overview

v0.8.1 is a hotfix release that addresses four bugs discovered after v0.8.0 shipped
and adds two feature improvements. The fixes cover: richer error detail when a crew
gateway rejects a request, a Caddy CA certificate volume name mismatch in status
output, Python bytecode leaking into Academy skill deliveries, and misleading wording
in Raven's order templates. The two feature additions are the `ghostship-spawn` Academy
skill for safe named-persona dispatch (resolving the Captain autopilot gap on non-kiro
backend crews) and Academy backend delivery to all harnesses, not only kiro.

---

## New

### `ghostship-spawn` Academy skill (TRN-263)

`ghostship-spawn` is a new Academy skill copied into every crew at launch. It provides
the four gateway operations that were previously unavailable to agents without
hand-crafted REST calls: named-persona dispatch, task detail, steering, and
continuation. The helper sends cookie-authenticated requests to the crew's fixed
loopback gateway only — agents do not assemble raw REST calls or handle session cookies
directly.

With this skill in place, Raven dispatches worker personas through the helper rather
than via hand-built gateway calls. This resolves the Captain autopilot gap that
previously prevented the `sdd` and `independent-review` templates from working on
Claude and Codex backend crews.

See the [Architecture — Ghostship-spawn gateway skill](architecture.md#ghostship-spawn-gateway-skill)
section for full details.

### Academy backend delivery to all harnesses (TRN-264)

Academy skills, steering documents, and MCP server configuration now reach every
harness in the crew, not only kiro. At launch the transport stages Academy assets into
`~/.agents/` and runs `.agents/setup`, which wires them into the native paths of every
harness detected in the image — for example `~/.claude/skills/` and `~/.claude/rules/`
for Claude Code.

Claude crews previously received none of the Academy skills or steering docs. After
upgrading, relaunch existing claude-backend crews so they pick up the new delivery
mechanism.

Agent persona JSON files (`academy/agents/*.json`) continue to be delivered to
`~/.kiro/agents/` on every backend — the gateway reads this directory to resolve named
dispatch for claude and codex crews as well as kiro.

---

## Fixed

### Gateway error detail now includes HTTP status and response body

When a crew gateway rejects a request and recovery gives up, the error returned to MCP
callers now includes the gateway's HTTP status code and response body (redacted, up to
500 characters). Previously, all rejection cases surfaced only the generic "crew …
is unresponsive" message — making a plain rejection such as `Agent 'ghost' not found`
indistinguishable from a genuine connectivity failure. Rejected requests now say so
explicitly, instead of suggesting a crew health check.

### Caddy CA certificate volume name corrected

`ghostship status` and the install output now correctly show the Caddy CA certificate
path. Both previously looked up the volume as `ga-portal-data`, but Compose creates it
as `ga_ga-portal-data`. The lookup now uses the correct name, so the cert path shown
in status output can be used directly with `caddy trust`.

### Academy skill bytecode excluded from crew delivery

Academy skills no longer carry Python bytecode (`__pycache__/` directories and `*.pyc`
files) into crew containers. Previously, any compiled bytecode present in the local
Academy checkout was copied verbatim, which could trigger import warnings and wasted
space.

### Raven order-template wording clarified

The `sdd` and `independent-review` order templates now tell Raven explicitly that a
change's artifacts describe the _target_ behaviour after the change is applied, not
the current live behaviour. This prevents a self-referential hold where a change that
rewrites Raven's own rules caused Raven to treat the unmerged new rules as the current
standing order.

---

## Resolved Limitations

### Captain autopilot on Claude/Codex backends (from v0.6.0, v0.8.0)

**Resolved by TRN-263 (`ghostship-spawn`).**

The v0.6.0 release noted that Captain autopilot did not work on Claude or Codex backend
crews because Raven could not make the authenticated gateway calls needed by the `sdd`
and `independent-review` templates. This is now fixed: the `ghostship-spawn` skill
provides a cookie-authenticated helper that any agent can invoke without constructing
raw REST calls or managing session cookies, so the Captain loop works on all backends.

Relaunch existing non-kiro crews after `ghostship upgrade` so they receive the helper.

### Claude Code attribution on commits (from v0.8.0)

**Resolved by TRN-264 (academy backend delivery).**

Claude-backend crews previously added Claude Code attribution trailers to commits and
PR descriptions (`Co-Authored-By` and "Generated with Claude Code" text) because the
setting to suppress this was not being baked into the crew image. The setting is now
applied at image build time. Relaunch existing claude-backend crews after
`ghostship upgrade` to pick up the corrected image.

---

## Upgrading

Run `ghostship upgrade` to rebuild images and restart the transport. If you use
Claude or Codex backend crews, also relaunch them after upgrading so they receive the
`ghostship-spawn` skill and the corrected Academy delivery path:

```bash
ghostship upgrade
# Then, for each claude/codex crew:
nuke(crew_id, confirm=True)
launch(crew_id, backend="claude")   # or "codex"
```

See [docs/configuration.md](configuration.md) for the full variable reference, and
[docs/auth.md](auth.md) for credential management.
