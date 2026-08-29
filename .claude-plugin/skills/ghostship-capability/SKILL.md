---
name: ghostship-capability
description: Configure what ghostship crews can do — agent personas, skills, steering, MCP server catalogue, security policies, crew compositions, and environment variables. Use when the task is about changing what agents know or can access, adding a new composition, wiring an MCP server into the catalogue, or tuning configuration — not about installing ghostship (ghostship-admin) or driving an already-running fleet (ghostship-command).
metadata:
  author: ghostship
  version: "0.2.0"
---

# Ghostship Capability

The Ghost Academy (`academy/`) defines the capabilities available to every
crew — agent personas, skills, steering, orders, MCP servers, and security
policies. `crews/` defines the compositions (crew types) that package those
capabilities.

**All capability changes require `./install.sh` to take effect.** The install
copies `academy/` and `crews/` into the transport data volume. Edits to repo
files have no effect until you reinstall.

Requires the ghostship repo on disk. Default location: `~/.ghostship/ghostship`.

---

## Academy structure

```
academy/
  agents/          ← agent persona JSON files
  skills/          ← skill SKILL.md files
  steering/        ← persistent context loaded into every agent session
  orders/          ← captain standing-order templates
  policies/        ← security policy variants
  mcp/             ← MCP server catalogue

crews/
  spec-ops/
    Containerfile  ← crew image
    manifest.json  ← what agents/skills/steering/MCP servers to load
  _base/           ← shared base layers (don't edit)
```

---

## How to add or customise an agent persona

Each file in `academy/agents/` configures one agent. The filename (without
`.json`) is the agent name used in `dispatch(agent="<name>")`.

**Edit an existing persona** — open `academy/agents/ghost.json` and change
the `prompt`, `model`, or `tools` fields. Be careful editing `prompt` on the
six built-in personas — they carry carefully tuned OpenSpec workflow
instructions. Add new behaviour at the end of the prompt rather than
replacing existing guidance.

**Add a new persona** — create `academy/agents/<name>.json`:

```json
{
  "name": "scout",
  "model": "gpt-5.6-luna",
  "prompt": "You are Scout. Your job is to...",
  "tools": ["read", "web_search", "web_fetch"]
}
```

Then add `"scout"` to `manifest.json`'s `agents` list (or keep `"*"` to
load all agents automatically).

**Change the default model** — either edit the `model` field per-agent, or
set `KC_MODEL_OVERRIDE` / `KC_MODEL_DEFAULT` in `ghostship.conf` to apply
globally without touching agent files.

---

## How to add a skill

Skills are Markdown files injected into agent context at dispatch time.
A skill lives at `academy/skills/<skill-name>/SKILL.md`.

**Create a new skill:**

```bash
mkdir -p academy/skills/my-skill
cat > academy/skills/my-skill/SKILL.md << 'EOF'
---
name: my-skill
description: What this skill does and when to use it.
---

# My Skill

Instructions for the agent...
EOF
```

**Wire it to an agent** — add `{{SKILL:my-skill}}` to the relevant agent's
`prompt` field in their JSON file. The transport substitutes the full skill
content at dispatch time.

Skills load on demand by keyword trigger in most harnesses — check
`academy/skills/INTERNAL_SKILLS.md` for the index of built-ins and the
convention for naming and structuring skill files.

---

## How to customise steering

`academy/steering/STANDING_ORDERS.md` is loaded into every agent session in
a crew. It contains fleet-wide operational rules — dispatch coordination,
deduplication protocol, the SDD lifecycle conventions.

Edit it to change how all agents in every crew behave by default. Use skills
for persona-specific guidance; use steering only for genuinely fleet-wide rules.

**Add a new steering file** — drop any `.md` file into `academy/steering/`.
All files in that directory are loaded automatically.

---

## How to add a captain order template

Templates live in `academy/orders/` as Markdown files. The filename without
`.md` is the template name used in `captain(template="<name>")`.

**Create a new template:**

```bash
cat > academy/orders/my-workflow.md << 'EOF'
---
description: "Run a nightly audit of the codebase."
---
Run a nightly audit of the codebase at path ~/workplace/kirocrew-workspace/repo.

{{RAVEN_GATEWAY_ORIENTATION}}

{{RAVEN_STORE_RESOLUTION}}

Each check-in, dispatch Wraith to audit for [specific concern]. When findings
exist, dispatch Ghost to fix them. When nothing to fix, escalate to Admiral.

{{RAVEN_SELF_CANCEL}}
EOF
```

The `{{RAVEN_GATEWAY_ORIENTATION}}`, `{{RAVEN_STORE_RESOLUTION}}`, and
`{{RAVEN_SELF_CANCEL}}` placeholders are substituted by the transport at
order-write time — always include them in custom templates so Raven has the
correct operational context.

---

## How to add an MCP server to the catalogue

MCP servers available to crews live in `academy/mcp/`. Each `.json` file
defines one server; the filename without `.json` is the server name.

**Add a new server:**

```bash
cat > academy/mcp/my-server.json << 'EOF'
{
  "type": "stdio",
  "command": "npx",
  "args": ["@my-org/my-mcp-server"]
}
EOF
```

For HTTP servers:

```json
{
  "type": "http",
  "url": "http://my-server.example.com/mcp",
  "headers": {
    "Authorization": "Bearer ${MY_SERVER_TOKEN}"
  }
}
```

Secrets like `${MY_SERVER_TOKEN}` are resolved from the transport environment
at crew setup time — set them in `ghostship.conf`:

```bash
# ghostship.conf
MY_SERVER_TOKEN="sk-..."
```

Servers with a `headers` field are automatically marked `poolable: false`
(they carry per-session credentials and can't be shared across sessions).

**Wire the server to a composition** — add its name to the `mcpServers` list
in the relevant `manifest.json`:

```json
{
  "agents": "*",
  "skills": "*",
  "steering": "*",
  "mcpServers": ["my-server", "playwright"]
}
```

An empty `[]` means no MCP servers. The field must be present.

---

## How to build a new crew composition

A composition is a named crew type. To create one:

**1. Create the directory:**

```bash
mkdir -p crews/my-composition
```

**2. Write the Containerfile** — start from the spec-ops base or build your
own. Minimum viable composition reuses the spec-ops image:

```dockerfile
# crews/my-composition/Containerfile
FROM localhost/spec-ops:latest
# Add any extra tooling this composition needs
RUN apt-get install -y my-tool
```

Or start from the KiroCrew base directly:

```dockerfile
FROM ghcr.io/kirodotdev/kirocrew:0.4.0
# Install mail stack, kiro-cli, openspec, any extra tools...
```

**3. Write the manifest:**

```json
{
  "agents": ["ghost", "raven"],
  "skills": "*",
  "steering": "*",
  "mcpServers": ["my-server"]
}
```

- `"agents": "*"` loads all agents in `academy/agents/`; pass a list to restrict
- `"skills": "*"` loads all skills; pass a list to restrict
- `"steering": "*"` loads all steering files; pass a list to restrict
- `"mcpServers": []` is required (even if empty)

**4. Rebuild:**

```bash
./install.sh
```

This builds the new image as `localhost/my-composition:latest` and registers
the composition. It's now available as `launch(crew_id="...", composition="my-composition")`.

---

## How to apply changes

```bash
cd ~/.ghostship/ghostship   # or wherever your repo lives
./install.sh                # rebuilds images + recopies academy/ and crews/
```

Running crews pick up academy changes on their next container restart —
stopped crews get the new academy automatically when they next start.
Currently running crews won't pick up changes until restarted.

**Crew image changes** (edited Containerfile) require existing crews to be
nuked and relaunched — `evac` anything needed first, then
`nuke(crew_id, confirm=True)` and `launch(crew_id)` over MCP.

---

## Configuration — `ghostship.conf`

Operator-level env vars that tune transport behaviour. Copy the example and
edit only what you need:

```bash
cp config/ghostship.conf.example config/ghostship.conf
./install.sh --config config/ghostship.conf
```

Key variables (full reference: `docs/configuration.md`):

| Variable | Purpose |
|:---------|:--------|
| `KC_MODEL_OVERRIDE` | Force a specific model for all crew agents |
| `KC_MODEL_DEFAULT` | Global model fallback (lower precedence than per-agent `model`) |
| `GA_API_KEY` | Bearer key locking the MCP/REST endpoint |
| `GA_MAX_ACTIVE_CREWS` | Max simultaneously running crew containers |
| `GA_MIN_FREE_MEM_GB` | Memory floor before a new crew is allowed to start |
| `GA_IDLE_STOP_SECS` | Seconds idle before a crew container is stopped |

Secrets referenced in the MCP catalogue (e.g. `${MY_TOKEN}`) must be set
here — they're injected into the transport environment at install time.
