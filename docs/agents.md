# Agents

Every ghostship ships the same six KiroCrew agent personas, defined in
[`academy/agents/`](../academy/agents/) and copied into each crew on `launch`
(see [architecture.md](architecture.md#crew-lifecycle), step 9).

| Agent | Role | OpenSpec ops |
|:------|:-----|:-------------|
| **Ghost** | General-purpose operative — executes one well-scoped task end to end | all six |
| **Spectre** | Planning operative — investigates, scaffolds proposals, revises plans | explore, propose, update-change |
| **Banshee** | Review/fix operative — independent second pass; finds bugs, runs tests, traces to root | explore, propose, update-change, apply-change |
| **Reaper** | Cleanup operative — closes out finished changes | sync-specs, archive-change |
| **Wraith** | Recon/docs operative — research and docs writing; read-only over code | explore |
| **Raven** | Watcher/coordinator — skims mailboxes, checks task state, dispatches bounded next steps. Captain-loop behaviour injected via standing-order template. | dispatch via `kirocrew` CLI + `ghostship-spawn` skill |

Tool grants differ per worker. Ghost, Spectre, and Banshee have the full set (`read grep glob write code shell web_search web_fetch`); Reaper has all except `code` (`read grep glob write shell web_search web_fetch`); Wraith has `read grep glob shell web_search web_fetch` (no `write`, no `code`). Raven has `read grep glob shell` only.

The five workers form the OpenSpec cycle: Spectre explores and proposes, Ghost implements, Banshee reviews and fixes independently, Reaper syncs and archives, Wraith researches and documents. Raven is outside that cycle — it's the persona the Captain check-in loop dispatches each tick.

Ghost is the one agent with the full OpenSpec lifecycle (explore through archive), so a well-scoped task is drivable end to end without a hand-off. Banshee gets explore through apply-change — an independent reviewer hands fixes to Reaper to formally close out. Banshee's preferred pattern is to amend the existing change via `openspec-update-change` when the fix fits, or `openspec-propose` when it doesn't.

Small, self-contained work can start and end with a single Ghost. Not every task needs the full cycle.

## Academy delivery (TRN-264)

Academy content — skills, steering docs, and MCP servers — is delivered to the
backend-native harness paths of every crew via `mcteamstar/.agents`, which is
baked into every crew image at build time as `/home/kirocrew/.agents`.

At crew launch, `AcademyLoader` stages manifest-selected content into the
in-container `.agents/` staging directories:

| Content | Staged path | kiro harness | claude harness |
|:--------|:------------|:-------------|:---------------|
| Skills | `.agents/skills/<name>/` | `~/.kiro/skills/<name>/` | `~/.claude/skills/<name>/` |
| Steering | `.agents/context/<name>.md` | `~/.kiro/steering/<name>.md` | `~/.claude/rules/<name>.md` |
| MCP config | `.agents/mcp/servers.json` | `~/.kiro/mcp.json` | `~/.claude.json` |

After staging, `AcademyLoader` calls `.agents/setup` inside the container with
no harness argument. Setup detects which harnesses are installed in the image and
wires the staged content to each one's native paths, whatever the crew's own
backend.
New backends (e.g. `codex`, `opencode`) require no ghostship changes — only an
update to `mcteamstar/.agents/setup`.

**Agent persona JSON** (`academy/agents/*.json`) is delivered directly to
`~/.kiro/agents/` for every crew, whatever its backend. That directory is
KiroCrew's persona registry: the gateway reads it on every backend to resolve
named dispatch (`ghost`, `raven`, ...) and to build each session's persona
prompt. Without it, a claude or codex crew refuses every named dispatch.

## Captain

Captain adds one autonomous mechanism on top of manual dispatch: a recurring `/api/crons` job named `captain` that dispatches Raven in a persistent session.

- **Free-form order:** `captain(crew_id, action="order", message="<order>", interval=<n>)` — or pass a cron expression.
- **SDD template:** `captain(crew_id, action="order", template="sdd", change_name="<change>", interval=<n>)`. Directs Raven to read the change's OpenSpec status and `tasks.md` each tick, then dispatch Spectre for incomplete planning, Ghost for unchecked tasks, Banshee for independent review, and Reaper to sync and archive after a clean review. After one fix-and-re-review cycle with unresolved findings, Raven escalates to the Admiral. `change_name` accepts a single name or comma-separated list; multiple changes run in parallel with automatic worktree isolation and merge reconciliation.
- **`independent-review` template:** `captain(crew_id, action="order", template="independent-review", interval=<n>)`. Each tick dispatches four concurrent reviewers (Banshee × 3 for security/quality/test-coverage; Wraith for docs) and mails a consolidated summary to the Admiral. Omit `change_name` to review the entire codebase.

Both forms append the resolved order to `captain@localhost`. `captain(..., action="status")` reports the job's enabled state, last-run summary, and mailbox counts. `action="stop"` pauses the cron with history intact.

`transport://orders` returns a summary index; `transport://orders/{name}` returns the full resolved body.

**Claude-backend support:** Captain autopilot now dispatches through the manifest-delivered `ghostship-spawn` skill, so Raven no longer needs the gateway's local IPC secret. Relaunch an existing crew after upgrading so it receives the helper and refreshed Raven prompt. Manual relay (`dispatch`, `pickup`, `steer`) remains available when an operator intentionally chooses not to run the Captain loop.

## Steering, not enforcement

The `tools`/`allowedTools` arrays in each agent JSON are a real technical gate. The "OpenSpec ops" column above is not: skills are copied crew-wide, and a custom agent inherits every default resource — including every skill — unless `chat.disableInheritingDefaultResources` is set *and* the agent defines its own `resources` list. None of the six currently do. The division is enforced only by each agent's system prompt. Raven's five-worker roster is similarly prompt-level; transport's allowlist enforces all six names for `dispatch` and `schedule`.

Not yet built: per-agent skill scoping via `resources`/`skill://` and per-crew workspace seeding. Revisit if role bleed becomes a problem.
