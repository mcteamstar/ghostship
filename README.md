![Ghostship](docs/ghostship.png)

*Launch a Ghostship from the Ghost Academy and command the crew.*

A multi-agent orchestration system for [KiroCrew](https://github.com/kirodotdev/KiroCrew) over MCP.
Customise shared agent personas, skills, and steering.
Runs locally on macOS or Linux using Podman.

## Why Ghostship?

KiroCrew is designed for running fleets of agents over long horizon tasks, but running KiroCrew on your desktop limits you to one instance, directly on your filesystem, with low isolation between crewmates.

`ghostship` runs each crew in its own container and isolates workspaces with podman volumes. Crews are persistent workspaces — summoned once (`launch`) and reusable across multiple features, with idle-stop handling resource management transparently.
Command your crews over MCP from any agent. Multiple crews can run side by side without colliding, with fresh context and curated capabilities.

`crews` here are designed for **Spectre-Driven Development** based off [OpenSpec](https://github.com/Fission-AI/OpenSpec). In particular, Kiro is both a fast and cost-efficient workhorse for executing well-defined change specs, and versatile enough to handle the whole cycle when needed. Agents default to `gpt-5.6-luna` but this is configurable via the `--model` flag (see [docs/configuration.md](docs/configuration.md)).

## Install

### Prerequisites

- macOS or Linux
- Podman — installed automatically if missing (Homebrew on macOS, `apt` or
  `dnf` on Linux; other distros: see [docs/manual-install.md](docs/manual-install.md))
- A kiro-cli identity — either the default Builder ID (free tier), or an
  org-licensed IAM Identity Center login (see [docs/auth.md](docs/auth.md))

**Linux platform support:** Verified on Ubuntu 22.04+ (apt) and Fedora 39+
(dnf, SELinux enforcing). Other distributions work if Podman >= 4.0 is
available — see [docs/manual-install.md](docs/manual-install.md) for
requirements and example commands. Requires cgroup v2 and Podman rootless.

### Setup

```bash
./install.sh
```

Installs Podman if missing, sets it up (on macOS: a `podman machine` VM,
since macOS has no container-capable kernel of its own; on Linux: directly
on the host, no VM), builds the transport and crew images, and runs the
`ga-transport` container bound to `localhost:64057` (MCP) and `localhost:64058`
(files).

If your kiro-cli login needs a specific identity provider, pass it directly
or let the script prompt you:

```bash
./install.sh --identity-provider <url> --region <region>
```

To run on a different port (the file server always follows at `port+1`):

```bash
./install.sh --port <port>
```

Full resolution order (config file → flags → interactive prompt) and all
environment variables: [docs/configuration.md](docs/configuration.md).

### Connecting to a harness

`ghostship` speaks MCP over streamable HTTP at `http://localhost:64057/mcp`
— no auth required, it's bound to `localhost` only.

If you enabled API-key authentication (`./install.sh --api-key <key>`), add
the `Authorization: Bearer <key>` header to every client — see
[docs/auth.md](docs/auth.md) for details and TLS guidance.

**kiro-cli:**
```bash
# Without API key:
kiro-cli mcp add --name ghostship --url http://localhost:64057/mcp --scope global

# With API key (set GHOSTSHIP_API_KEY in your environment):
kiro-cli mcp add --name ghostship --url http://localhost:64057/mcp \
  --headers '{"Authorization": "Bearer ${GHOSTSHIP_API_KEY}"}' --scope global
```

**Claude Code** — add to `~/.claude.json`'s `mcpServers`:
```json
"ghostship": {
  "type": "http",
  "url": "http://localhost:64057/mcp",
  "headers": { "Authorization": "Bearer ${GHOSTSHIP_API_KEY}" }
}
```
Omit the `headers` field if API-key auth is disabled.

**Any other MCP client** — same URL, streamable-HTTP transport. When API-key
auth is enabled, send `Authorization: Bearer <key>` on every MCP request.
Use TLS or a trusted encrypted network if exposing the endpoint beyond localhost.

First `launch` triggers a kiro-cli device auth prompt — see
[docs/auth.md](docs/auth.md).

## Ghost Academy

Every ghostship runs the same curriculum — agent personas, skills, and
steering — copied in at `launch`. See
[docs/architecture.md](docs/architecture.md) for how `ga-transport` manages
the containers underneath.

### Tools

Registered as `ghostship`:

Ship operations (the crew container itself) come first, then crew operations
(the personas and tasks running inside it):

| Tool | Description |
|:-----|:------------|
| `crews` | List all registered crews and their status. |
| `launch` | Summon a new crew container + workspace. Repository seeding is a separate step. |
| `supply` | Deliver a file, tar archive, or git bundle into a crew's workspace via a presigned upload URL. |
| `evac` | Extract a file, git diff, or git bundle from a crew's workspace. |
| `nuke` | Destroy a crew (container + both volumes). Requires `confirm=True`. |
| `captain` | Manage a crew's order; `order` sets or updates it, `stop`/`status` pause and check it, and the built-in `sdd` template covers standard OpenSpec lifecycle work. |
| `schedule` | Book a recurring task on a crew (cron or interval); recurring work defaults to Ghost; pass Raven explicitly for a Captain check-in. |
| `dispatch` | Spawn a task on one of the six agent personas (below) in a named crew. |
| `steer` | Guide a running task or continue a completed one with new context; use `force=True` to hard-stop a running task before continuing it. |
| `pickup` | Check progress or collect result; always includes mail state. `timeout_secs=0` (default) checks once immediately; `timeout_secs=N` polls until done or timeout (also: bridge, watch, monitor, patrol, poll). Without `task_id`: list all tasks. |

### Seed or extract a Git repository

`launch` creates the crew and its empty workspace; it does not clone a
repository. To seed a checkout with its real commit history, create a bundle
locally and upload it after `launch` returns a ready crew:

```bash
# On the caller's machine
git bundle create ./project.bundle --all

# Ask the transport for supply(path="repo", crew_id="my-crew", bundle=True),
# then upload the returned delivery_url.
curl -X POST "<delivery_url>" --data-binary @./project.bundle
```

To extract history from the crew, ask for `evac(path="repo",
crew_id="my-crew", bundle=True)`, download the returned URL, and consume the
bundle as a normal Git source:

```bash
curl -fsSL "<evac_url>" -o ./crew.bundle
git clone ./crew.bundle ./crew-repo

# For an existing checkout, fetch an advertised ref from the bundle instead.
git bundle list-heads ./crew.bundle
git fetch ./crew.bundle refs/heads/main:refs/remotes/crew/main
```

For an incremental transfer, create a range bundle such as
`git bundle create ./changes.bundle old-ref..new-ref`; a receiver must already
have the prerequisite `old-ref` before fetching that bundle.

### Agents

Every ghostship ships the same six KiroCrew agent personas — the Ghost
Academy's curriculum. The five worker personas split up
[OpenSpec](https://github.com/Fission-AI/OpenSpec)'s spec-driven workflow —
explore → propose → apply → archive — between them, while Raven coordinates
standing orders without implementing work. See
[docs/agents.md](docs/agents.md) for tool grants and enforcement details.

| Agent | Role | Owns |
|:------|:-----|:-----|
| **Spectre** | Planning operative — investigates, scaffolds proposals, revises plans as understanding evolves | `openspec-explore`, `openspec-propose`, `openspec-update-change` |
| **Ghost** | General-purpose precision operative — executes one well-scoped task or brief end to end, including implementing a change's tasks | all six OpenSpec operations |
| **Banshee** | Independent review/fix operative — a second pair of eyes across a wider field than Ghost's single task; finds bugs, runs tests, traces to root | `openspec-explore`, `openspec-propose`, `openspec-update-change`, `openspec-apply-change` |
| **Reaper** | Cleanup operative — closes out finished changes | `openspec-sync-specs`, `openspec-archive-change` |
| **Wraith** | Recon and documentation operative — research, investigation, writing project docs; read-only over code | none (adjacent) |
| **Raven** | Watcher and messenger for the Captain's recurring loop — skims mailboxes, assesses the crew, and dispatches bounded worker steps | dispatch via the `kirocrew` CLI and gateway REST API; prompt-restricted to the five worker personas |

### Spectre Driven Development

A full pass, start to finish — left of the divider is the Admiral (you,
issuing MCP calls); right of it is the ghostship itself, alive from
`launch` until you intentionally tear it down with `nuke`:

```
ADMIRAL  (your MCP client)                  │  GHOSTSHIP  (crew container + workspace)
────────────────────────────────────────────┼───────────────────────────────────────────────────
                                            │                                                  │
launch(crew_id)                             ┌──────────────────────────────────────────────────┐
                                            │   container + workspace created                  │
                                            │                                                  │
dispatch(spectre, "explore + propose")      ──► Spectre drafts a spec-backed proposal          │
                                            │                                                  │
pickup(task_id)                             ◄── proposal ready to review                       │
 ▲                                          │                                                  │
 │   not happy yet? revise it:              │                                                  │
 └───────────────────┐                      │                                                  │
                     ▼                      │                                                  │
dispatch(spectre, "update-change")          ──► plan revised                                   │
                                            │                                                  │
dispatch(ghost, "apply-change")             ──► Ghost implements the change                    │
                                            │                                                  │
dispatch(banshee, "review")                 ──► optional independent pass — finds + fixes bugs │
                                            │                                                  │
dispatch(reaper, "sync-specs + archive")    ──► specs synced, change archived                  │
                                            │                                                  │
evac(path)                                  ◄── pull the finished diff or file out             │
                                            │                                                  │
                          ↺ repeat for the next change — crew persists                        │
                                            └──────────────────────────────────────────────────┘
```

Crews persist across changes. After `evac`, the crew remains live and ready for the next feature — there is no need to tear it down between tasks. The idle-stop mechanism handles resource management automatically: inactive crews stop after a timeout and restart transparently on the next command. `nuke` exists for intentional permanent workspace destruction — when you want to discard a crew's volumes, history, and context entirely — not as a routine post-task step.

`pickup(task_id)` polls after every `dispatch` above, not just the first —
shown once here for brevity, with a loop-back on `update-change` since
that's the step you're most likely to repeat. `crews()` lists every
registered crew and its status at any point in the lifecycle.

Captain has one autonomous mechanism per crew: a recurring Raven check-in.
For an open-ended objective, call `captain(crew_id, action="order",
message="<standing order>", interval=<n>)` or provide a cron expression. For
standard OpenSpec lifecycle work, use
`captain(crew_id, action="order", template="sdd", change_name="<change>",
interval=<n>)`; the built-in template makes Raven read real OpenSpec and
`tasks.md` state, dispatch the next sanctioned persona, review independently,
and sync/archive only after a clean review. When `interval` is set, Raven is
also dispatched once immediately on creation (before the first interval tick)
by default — pass `fire_immediately=False` to suppress this, or
`fire_immediately=True` with a cron expression to opt in. The transport writes
the resolved order to `captain@localhost` and ensures one persistent Raven
check-in; `status` reports job enablement, last-run summary, and both Captain
and Admiral mailbox counts, while `stop` pauses the job without deleting its
history. The `transport://agents` resource lists available personas and
`transport://orders` lists built-in standing-order templates. A scheduled
check-in has a `job_id`, not a dispatch `task_id`, so `steer` is not its
control channel.

## Further reading

- [docs/architecture.md](docs/architecture.md) — components, crew lifecycle, idle-stop/auto-restart, reboot recovery, project layout
- [docs/agents.md](docs/agents.md) — the six agent personas, what each owns in the OpenSpec workflow, and how that's enforced (and isn't)
- [docs/auth.md](docs/auth.md) — auth flow, identity provider config, secret rotation
- [docs/configuration.md](docs/configuration.md) — full environment variable reference, extending the crew image
