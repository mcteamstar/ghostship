---
name: ghostship-admin
description: Install, configure, connect a client to, upgrade, or tear down a ghostship transport — Podman prerequisites, the `ghostship` CLI (`ghostship install`/`ghostship start`/`ghostship uninstall`/`ghostship init`/`ghostship status`), the transport's own API-key auth, and rebuilding images. Use when there's no MCP connection to `ghostship` yet, or when the task is about the transport host itself (bringing it up, connecting a new client, upgrading, tearing it down) rather than driving an already-running fleet — for that, use `ghostship-command` instead.
metadata:
  author: ghostship
  version: "0.2.3"
---

# Ghostship Admin

## Quick reference: CLI entry points

If ghostship is already installed and the `ghostship` command is on your PATH,
use the CLI for the most common tasks:

```bash
# Health check — see if the transport is running, what port, how long
ghostship status

# Wire MCP server + skill symlinks for all detected agent clients (one-time, idempotent)
ghostship init

# Target a specific client, optionally with a custom URL or API key
ghostship init --agent kiro
ghostship init --agent claude --url http://myhost:64057/mcp --api-key <key>
```

`ghostship status` is the canonical health check — it reads the container state
directly via Podman, with no MCP connection required.

`ghostship init` automates everything in [Connect an MCP client](#connect-an-mcp-client)
below: registers the MCP server and symlinks the three skill files for each detected
agent client. It is idempotent — safe to run again after a reinstall or repo move.

The rest of this skill covers the full manual setup path and advanced scenarios.

## Get ghostship

Before anything else, check whether ghostship is already installed:

```bash
ls ~/.ghostship/ghostship 2>/dev/null && echo "already cloned" || echo "not yet cloned"
```

If it's already there, skip to [Install](#install) or [Connect an MCP client](#connect-an-mcp-client)
depending on what you need.

If not, **ask the user where they'd like to store ghostship.** The recommended
default is `~/.ghostship` — it's a clean, predictable home for the repo and
any future persistent data (config, credentials cache, etc.):

```bash
# Default — recommended
mkdir -p ~/.ghostship
git clone https://github.com/mcteamstar/ghostship.git ~/.ghostship/ghostship
cd ~/.ghostship/ghostship
```

If the user prefers a different location (e.g. `~/development/ghostship` or
`~/projects/ghostship`), clone there instead — just make sure to note the
path, as `./install.sh` must be run from inside it and `ghostship start` needs to
find it again later.



This skill is for standing a ghostship transport up, connecting a client to
it, keeping it running, and taking it down — the host-level, shell-driven
work that happens *before* an MCP connection exists. Once a client is
connected and the `ghostship` MCP tools are available, switch to
`ghostship-command` for everything about driving the fleet itself; nothing
here duplicates that.

Requires shell access (`Bash`) to the machine running ghostship — macOS or
Linux, with Podman. This skill doesn't run over MCP, because at install
time there usually isn't an MCP connection yet.

## Two separate auth layers — don't conflate them

Ghostship has two independent auth concerns, and both are this skill's job
to set up — neither is `ghostship-command`'s:

1. **The transport's own endpoint auth** — an optional API key that locks
   down the MCP/REST/file-transfer endpoint itself. See "Lock down the
   endpoint" below.
2. **kiro-cli identity** (Builder ID or IAM Identity Center) — used by crew
   containers to run Kiro. Set this up explicitly with the `/login` flow
   below, before ever calling `launch()`. `launch()` does have its own
   fallback device-auth trigger if you skip this — that's `ghostship-command`
   territory once you're already connected — but it's a fallback, not the
   recommended path, and it's actively broken for IAM Identity Center
   installs (see the login section).

## Prerequisites

- macOS or Linux (cgroup v2, Podman rootless; verified on Ubuntu 22.04+).
- **Podman >= 4.4** — `brew install podman` (macOS) or
  `sudo apt-get install -y podman podman-compose` (Ubuntu/Debian).
- **`podman-compose`** — `brew install podman-compose` on macOS; included
  in the apt command above on Debian/Ubuntu.
- A kiro-cli identity to authenticate with (Builder ID free tier, or IAM
  Identity Center) — see layer 2 above; set it up with the `/login` flow
  below.

## Install

> ⚠️ **Authenticate before your first `launch`.** The `/login` kiro-cli
> auth flow (step 3 below) must complete *before* you ever call `launch()`.
> Calling `launch()` first fails with `not_authenticated`, and any crew
> partially created in that state can't be salvaged — it has to be nuked.
> Don't rely on `launch()`'s fallback auto-trigger to bootstrap auth for
> you; it's a fallback, not the recommended path, and it's actively broken
> for IAM Identity Center installs. Do the explicit `/login` flow first.

Setup is a five-step sequence — do them in order:

1. **Install Podman prerequisites** — see [Prerequisites](#prerequisites)
   below (Podman >= 4.4 and `podman-compose`).
2. **Run `./install.sh`** — builds images and starts the transport (this
   section).
3. **Complete the `/login` auth flow** — set up the kiro-cli identity
   *before your first `launch()`* (see [Log in](#log-in--kiro-cli-identity-do-this-before-your-first-launch)).
4. **Register the MCP client** — point your harness at the transport (see
   [Connect an MCP client](#connect-an-mcp-client)), then switch to
   `ghostship-command`.
5. **Switch to `ghostship-command`** — once the tools are visible, all fleet
   operations live there; this skill is only for host-level work after that.

### Step 2: run `./install.sh`

```bash
./install.sh
```

Builds the crew images and starts the `ga-transport` container, bound to
`localhost:64057` — MCP, the REST API, and file transfer all share that one
port.

For a repeatable setup, copy the example config first:

```bash
cp config/ghostship.conf.example config/ghostship.conf
# edit config/ghostship.conf, then:
./install.sh --config config/ghostship.conf
```

## Step 3: Log in — kiro-cli identity (do this before your first `launch`)

The transport exposes three plain HTTP routes on the MCP port for
academy-wide kiro-cli auth: `POST /login`, `GET /login`, `POST /logout`.
These are **not** MCP tools — no agent can call them, only `curl`/shell.
State machine:

```
UNAUTHENTICATED ──[POST /login]──► PENDING ──[GET /login → complete]──► AUTHENTICATED
                ◄─────────────────────[POST /logout]──────────────────────────┘
```

Recommended first-time flow, **before your first `launch()` call**:

```bash
# 1. Start the device-auth flow
curl -sX POST http://localhost:64057/login | jq
# → { "status": "pending", "login_url": "...", "code": "XXXX-XXXX" }

# 2. Open login_url in a browser, sign in, approve the device

# 3. Poll until complete
curl -s http://localhost:64057/login | jq .status
# → "complete"

# 4. Only now call launch()
```

Add `-H "Authorization: Bearer $GHOSTSHIP_API_KEY"` to every call above if
you've enabled the endpoint API key (see below).

**Don't skip this and call `launch()` first.** `launch()` has its own
fallback auto-trigger for first-time auth, but attempting `launch` before
auth is complete fails with `not_authenticated`, and any crew partially
created in that state can't be salvaged — it has to be nuked. Worse, for
`--license pro` (IAM Identity Center) installs, `launch()`'s fallback path
uses a non-TTY exec that can fail *silently* against the IdC device flow
(upstream bug [kirodotdev/Kiro#6120](https://github.com/kirodotdev/Kiro/issues/6120)).
The explicit `POST /login` flow above doesn't have that problem — always
use it, don't rely on `launch()` to bootstrap auth for you.

**Logout / secret rotation** — `POST /logout` clears the stored auth and
every running crew's kiro-cli auth rows, no nuke or relaunch required:

```bash
curl -sX POST http://localhost:64057/logout | jq
# → { "status": "logged_out" }
```

Use it to force a fresh login (logout, then repeat the flow above) when
tokens expire. Running crews get the new auth injected in place once
`GET /login` reports `complete`.

**Guards:** `POST /login` returns `409` if already authenticated (log out
first) or if a login is already in progress (poll instead). `GET /login`
returns `404` if no login is in progress. `POST /logout` returns `404` if
not currently authenticated.

## Lock down the endpoint — API key

An optional static bearer credential protecting the MCP/REST/file-transfer
endpoint itself (separate from kiro-cli identity above). Recommended for
any non-local deployment, optional for a local one:

```bash
./install.sh --api-key <key>
```

Persisted across future `install.sh` runs — you don't need to pass it
again. To rotate, run `./install.sh --api-key <new-key>` and update every
client's header; to disable, run `./install.sh --api-key ""` (empty
value). See `docs/auth.md` for how the key is stored and the full security
notes.

## Step 4: Connect an MCP client

Once the transport is up, register it as an MCP server in whatever client
will drive it. Without a key:

```bash
kiro-cli mcp add --name ghostship --url http://localhost:64057/mcp --scope global
```

With a key, the client needs the `Authorization` header configured too.
kiro-cli:

```bash
kiro-cli mcp add --name ghostship --url http://localhost:64057/mcp \
  --headers '{"Authorization": "Bearer ${GHOSTSHIP_API_KEY}"}' --scope global
```

Claude Code — add to `~/.claude.json`'s `mcpServers`:

```json
"ghostship": {
  "type": "http",
  "url": "http://localhost:64057/mcp",
  "headers": { "Authorization": "Bearer ${GHOSTSHIP_API_KEY}" }
}
```

Omit `headers` entirely if the endpoint has no key. Once this is done — the
`/login` flow above is complete and the client sees the `ghostship` tools —
**setup is finished: switch to `ghostship-command` for all fleet operations
(launch, supply, dispatch, pickup, steer, captain, evac, nuke).** You should
rarely return to `ghostship-admin` after this point, and only for host-level
work (upgrade, re-auth, teardown).

## Plumb the skill files into your agent

Registering the MCP server makes the *tools* available; it doesn't make
`ghostship-admin`/`ghostship-command` available as skills your agent will
actually read. That's a separate step. There's no single mechanism across
every harness — check your harness's own docs for where it reads `SKILL.md`
files from. Common paths:

- **Claude Code** reads skills from `~/.claude/skills/<name>/SKILL.md`
  (global) or `.claude/skills/<name>/SKILL.md` (project-scoped).
  Symlinks are followed, so link rather than copy to avoid drift:
  ```bash
  ln -s /path/to/ghostship/.claude-plugin/skills/ghostship-command \
        ~/.claude/skills/ghostship-command
  ln -s /path/to/ghostship/.claude-plugin/skills/ghostship-admin \
        ~/.claude/skills/ghostship-admin
  ```
- **Kiro** reads skills from `~/.kiro/skills/<name>/SKILL.md` (global).
  Same symlink pattern applies.
- **An Agent-Plugins-compatible client** can be pointed at the whole
  `.claude-plugin/` directory — `plugin.json` + `mcp.json` + `skills/`
  are discovered together. See `.claude-plugin/PACKAGING.md`.

Once skills are wired, your agent will use `ghostship-command` for all fleet
operations and `ghostship-admin` only for host-level work (install, auth,
upgrade). You should rarely need to invoke `ghostship-admin` after initial
setup is complete.

## Keep it running

`ghostship start` brings ghostship back up after a stop or reboot — starts the
Podman service (or machine, on macOS) and the `ga-transport` container.
Safe to run any time; it's a no-op if things are already running.

```bash
ghostship start                            # auto-discovers config
ghostship start --config ~/ghostship.conf  # explicit config
ghostship start --machine-name my-academy  # override machine name
```

Config is discovered in order: `<ghostship-dir>/ghostship.conf`, then
`~/ghostship.conf`, then `~/.config/ghostship/ghostship.conf`. If none is
found it prompts interactively; if several are found it lists them and
asks.

On Linux, `install.sh` enables linger (`loginctl enable-linger`) so a
headless/SSH-only host's Podman service and transport container survive
after the last login session ends — required for unattended operation, not
optional.

## Rebuild and upgrade

`podman start` (what idle-stop recovery and transport-restart use) restarts
an *existing* container from whatever image it was created from — it does
**not** pick up a rebuilt image. Only a fresh `podman run` does that:

| Rebuilt... | Needs recreating | How |
|:-----------|:------------------|:----|
| `transport/` (`localhost/transport:latest`) | The `ga-transport` container | `ghostship install` — removes and re-runs `ga-transport` unconditionally, no crew impact |
| `crews/spec-ops/Containerfile` (`localhost/spec-ops:latest`) | Each existing crew container | `nuke(crew_id, confirm=True)` then `launch(crew_id)` per crew, over MCP — destroys that crew's volumes, so `evac` anything needed first. This step is `ghostship-command`'s tool surface, not this skill's — mentioned here only because the trigger (a rebuilt crew image) is an admin-side event. |

## Uninstall

```bash
ghostship uninstall              # tears down transport
ghostship uninstall --purge-auth # also removes kiro-cli credentials
```

## Beyond the common path

Once ghostship is running and a client is connected, use **`ghostship-command`**
for all fleet operations (launch, dispatch, pickup, steer, captain, evac, nuke).

To configure what crews can do after installation — adding agent personas,
skills, MCP servers, or building new crew compositions — use
**`ghostship-capability`**.
