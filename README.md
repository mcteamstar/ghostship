![Ghostship](docs/images/ghostship.png)

*Launch Ghostships from the Ghost Academy and command the crew.*

A multi-agent orchestration system for [KiroCrew](https://github.com/kirodotdev/KiroCrew) over MCP.
Customise agent personas, skills and steering, then send them out into the unknown.
Runs locally and remotely on macOS or Linux using Podman.

[![tests](https://github.com/mcteamstar/ghostship/actions/workflows/test.yml/badge.svg)](https://github.com/mcteamstar/ghostship/actions/workflows/test.yml)

**Quick install (Claude Code plugin):**
```bash
claude plugin marketplace add mcteamstar/ghostship
claude plugin install ghostship@ghostship
```
Use `/ghostship-admin` for guided local setup, `/ghostship-capability` to customise the academy, and `/ghostship-command` to drive the fleet. See [Install](#install) below for full steps.

## Why Ghostship?

KiroCrew is built for long-horizon multi-agent tasks, but running it on your desktop gives you one instance, directly on your filesystem, with limited isolation between crewmates.

Ghostship runs each crew in its own container with a dedicated Podman volume. Each ship is a durable workspace — summoned once (`launch`), reusable across many features, idle-managed when not in use, and cleanly destroyable (`nuke`) at any time.

As **Admiral**, command your crews over MCP from any agent. Delegate to the crew's **Captain** or be the captain yourself. All ships in your *fleet* run side-by-side without colliding and can be tailored to your tactical needs.

The built-in `spec-ops` loadout is designed for **Spec-Driven Development** using [OpenSpec](https://github.com/Fission-AI/OpenSpec). Agents default to `gpt-5.6-luna` — configurable and overridable (see [docs/configuration.md](docs/configuration.md)).

### Why Not...

**Subagents?** Subagents are tied to your parent session and share your live workspace. Crew members are KiroCrew subagents running on a ghostship.

**Cloud Agents?** Cloud agents run on infrastructure outside your control. Ghostship crew images can be tailored to your needs within a security boundary you own, and can be hosted remotely like a private cloud agent.

**Agent Harnesses?** Ghostship is exactly the DIY orchestration layer for KiroCrew — parallelism, concurrency, and inter-agent communication — consumable by any agent over MCP.

## Install

### Prerequisites

- macOS or Linux
- **Podman >= 4.4** — `brew install podman` (macOS), `sudo apt-get install -y podman podman-compose` (Ubuntu/Debian)
- **`podman-compose`** — `brew install podman-compose` (macOS); included in the apt command above
- A kiro-cli identity — Builder ID / Social Login, or an IAM Identity Center account (see [docs/auth.md](docs/auth.md))

Other distros: [docs/manual-install.md](docs/manual-install.md). Requires cgroup v2 and Podman rootless. Verified on Ubuntu 22.04+.

> **Model access:** Ghostship defaults to `gpt-5.6-luna`, which requires a Pro subscription or higher. See [kiro.dev/docs/models](https://kiro.dev/docs/models/) for available models by tier, and [docs/configuration.md](docs/configuration.md) to override.

### Setup

```bash
./install.sh
```

Builds crew images, starts the `ga-transport` container, and starts `ga-portal` (Caddy) on `localhost:64057`. MCP, REST API, and file transfer all share this port. Caddy enforces `Authorization: Bearer` on `/mcp*` and `/files/*` when `GA_API_KEY` is set — see [docs/portal.md](docs/portal.md).

For a repeatable setup:
```bash
cp config/ghostship.conf.example config/ghostship.conf
# edit config/ghostship.conf, then:
./install.sh --config config/ghostship.conf
```

**API key** — locks the endpoint for any non-local deployment:
```bash
./install.sh --api-key <key>
```

**Client-only install** — connects to an already-running (usually remote) transport; skips all container infrastructure:
```bash
./install.sh --client-only --url https://academy.example.com/mcp
```
Add `--api-key <key>` if the remote transport requires a bearer token. Default URL: `http://localhost:64057/mcp`. See [Client-only install](docs/configuration.md#client-only-install).

To uninstall: `ghostship uninstall`. After a reboot, `ghostship start` brings it back without reinstalling.

**Updating `academy/` and `crews/`** — `./install.sh` snapshots these directories into the data volume. After editing files under either directory, re-run `./install.sh` for changes to take effect.

Full install options and environment variables: [docs/configuration.md](docs/configuration.md).

### Customising and forking

Run it as-is or make it your own. Once you add agent personas, skills, or new crew compositions, that configuration belongs in your own fork. See [docs/forks.md](docs/forks.md) for the fork model, visibility options, and keeping your fork current with upstream.

### Connecting to a harness

Before your first `launch`, complete the device auth flow — run `ghostship auth login`, or open the URL returned by `POST /login` or by calling `launch` without auth. See [docs/auth.md](docs/auth.md) for the walkthrough.

> **Shortcut:** `ghostship setup` automatically registers the MCP server and installs skill symlinks for detected agent clients (kiro-cli, Claude Code, opencode). Run it after `./install.sh`. It is idempotent — safe to re-run.

**Kiro (via Power):**

Install the ghostship power from the Powers panel → Add Custom Power → Import from GitHub:
```
https://github.com/mcteamstar/ghostship
```
The `ghostship-admin` skill walks you through the rest — Podman, `./install.sh`, auth, and connecting. See `.claude-plugin/PACKAGING.md` for keyed and remote installs.

**kiro-cli:**
```bash
# Without API key:
kiro-cli mcp add --name ghostship --url http://localhost:64057/mcp --scope global

# With API key:
kiro-cli mcp add --name ghostship --url http://localhost:64057/mcp \
  --headers '{"Authorization": "Bearer ${GHOSTSHIP_API_KEY}"}' --scope global
```

**Claude Code (plugin):** see the quick install command at the top of this README. It installs the three skills plus an unauthenticated connection to `http://localhost:64057/mcp`.

**Claude Code (manual, keyed, or remote)** — add to `~/.claude.json`'s `mcpServers`:
```json
"ghostship": {
  "type": "http",
  "url": "http://localhost:64057/mcp",
  "headers": { "Authorization": "Bearer ${GHOSTSHIP_API_KEY}" }
}
```
Omit `headers` if API-key auth is disabled.

For remote deployments, IAM Identity Center config, and TLS setup: [docs/configuration.md](docs/configuration.md) and [docs/auth.md](docs/auth.md).

### Skills

> **Strongly recommended:** install `ghostship-command` into your agent — it is the Admiral's fleet playbook. Without it you have the MCP tools but no guidance on using them effectively.

Skills follow the [Agent Skills](https://agentskills.io) standard and work in Claude Code, Kiro, and any harness that supports `SKILL.md`.

| Skill | What it does |
|:------|:-------------|
| `ghostship-command` | Drive the fleet — launch, seed, dispatch, steer, poll, autopilot, tear down. **Install this one.** |
| `ghostship-admin` | Install, configure, and connect a ghostship transport. |
| `ghostship-capability` | Configure agent personas, skills, crew compositions, MCP catalogue. |

**If you cloned the repo**, skills activate automatically under `.claude/skills/` (Claude Code) and `.kiro/skills/` (Kiro).

**Global install** (so your agent can use ghostship from any project):
```bash
# Claude Code
ln -s "$(pwd)/.claude-plugin/skills/ghostship-command" ~/.claude/skills/ghostship-command

# Kiro
ln -s "$(pwd)/.claude-plugin/skills/ghostship-command" ~/.kiro/skills/ghostship-command
```

The plugin install path (Claude Code plugin, Kiro Power) handles this automatically.

## Ghost Academy

Every ghostship has access to the same crew curriculum: agent personas, skills, and steering.

### Agents

Six agent personas. The five worker personas split up the [OpenSpec](https://github.com/Fission-AI/OpenSpec) spec-driven workflow.

| Agent | Name | Role |
|:-:|:------|:-----|
| <img src="docs/images/agent-spectre.png" width="256"> | **Spectre** | Planning operative — explores problems, scaffolds proposals, revises plans as understanding evolves |
| <img src="docs/images/agent-ghost.png" width="256"> | **Ghost** | General-purpose operative — executes one well-scoped task end to end; carries all six OpenSpec operations |
| <img src="docs/images/agent-banshee.png" width="256"> | **Banshee** | Review/fix operative — finds bugs, runs tests, traces to root, and fixes before shipping |
| <img src="docs/images/agent-reaper.png" width="256"> | **Reaper** | Cleanup operative — syncs delta specs to main specs and archives completed changes |
| <img src="docs/images/agent-wraith.png" width="256"> | **Wraith** | Recon and documentation operative — research, investigation, project docs; read-only over code and OpenSpec artifacts |
| <img src="docs/images/agent-raven.png" width="256"> | **Raven** | Watcher and messenger — skims crew mailboxes, checks task state, carries messages between personas and the Admiral |

See [docs/agents.md](docs/agents.md) for tool grants and enforcement details. See [docs/architecture.md](docs/architecture.md) for the full SDD workflow, git bundle seeding, and Captain supervision.

### MCP Tools

Registered as `ghostship`:

| Tool | Name | Description |
|:-:|:------|:-----|
| <img src="docs/images/tool-crews.png" width="256"> | `crews` | List all registered crews and their status. |
| <img src="docs/images/tool-launch.png" width="256"> | `launch` | Summon a new crew container + workspace. `composition` selects the crew type (default: `"spec-ops"`). `dashboard=True` allocates a port and returns a `dashboard_url`; default follows `GA_DASHBOARD_DEFAULT` (headless if unset). |
| <img src="docs/images/tool-supply.png" width="256"> | `supply` | Deliver a file, tar archive, or git bundle into a crew's workspace. |
| <img src="docs/images/tool-evac.png" width="256"> | `evac` | Extract a file, git diff, or git bundle from a crew's workspace. |
| <img src="docs/images/tool-nuke.png" width="256"> | `nuke` | Destroy a crew (container + both volumes). Requires `confirm=True`. |
| <img src="docs/images/tool-captain.png" width="256"> | `captain` | Manage a crew's standing order. Built-in templates: `sdd` (drives named OpenSpec changes through the Spectre → Ghost → Banshee → Reaper lifecycle; `change_name` accepts a name or comma-separated list) and `independent-review` (four concurrent reviewers — Wraith for docs, three Banshees for security/quality/test-coverage — mailing a consolidated report to the Admiral). |
| <img src="docs/images/tool-schedule.png" width="256"> | `schedule` | Book, cancel, or list recurring tasks. `action="create"` with `cron`, `interval`, or `delay`; `action="cancel"` by job_id; `action="list"` returns all active jobs. |
| <img src="docs/images/tool-dispatch.png" width="256"> | `dispatch` | Spawn a task on one of the six agent personas. Always immediate — returns a `task_id`. Pass `tasks=[...]` for atomic batch dispatch; response includes `batch_id` and per-task `task_ids`. `slot` controls which dashboard session the task attaches to (`None` headless, `"bridge"` shared, `True` auto-unique, `"<name>"` named). |
| <img src="docs/images/tool-steer.png" width="256"> | `steer` | Guide a running task or continue a completed one; `force=True` hard-stops before continuing. |
| <img src="docs/images/tool-pickup.png" width="256"> | `pickup` | Check progress or collect result. `timeout_secs=0` checks once; `timeout_secs=N` polls until done or timeout. Without `task_id`: list all tasks. |

## Further reading

- [docs/architecture.md](docs/architecture.md) — components, crew lifecycle, idle-stop/auto-restart, reboot recovery, project layout
- [docs/agents.md](docs/agents.md) — the six personas, OpenSpec ownership, and enforcement
- [docs/auth.md](docs/auth.md) — auth flow, identity provider config, secret management
- [docs/configuration.md](docs/configuration.md) — full environment variable reference, remote deployment, extending the crew image
- [docs/portal.md](docs/portal.md) — Caddy reverse proxy, TLS, dashboard sessions, auth upgrade paths
- [docs/forks.md](docs/forks.md) — fork model: visibility options, keeping current with upstream

### Route reference

The transport serves an OpenAPI 3.1.0 schema at **`GET /openapi.json`** (no auth required), generated at startup from the live route table and MCP tool registry.

```bash
curl -s http://localhost:64057/openapi.json | jq .paths
```
