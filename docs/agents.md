# Agents

Every ghostship ships the same six KiroCrew agent personas — the Ghost
Academy's curriculum, defined in [`academy/agents/`](../academy/agents/) and
copied into each crew on `launch` (see
[architecture.md](architecture.md#crew-lifecycle), step 9). The five worker
personas split up the [OpenSpec](https://github.com/Fission-AI/OpenSpec)
spec-driven workflow — explore → propose → apply → archive, plus update-change
and sync-specs — while Raven coordinates standing orders without implementing
work. The definitions are baked into the crew image (`crews/spec-ops/Containerfile`
installs the `openspec` CLI; the `openspec-*` skills under
[`academy/skills/`](../academy/skills/) shell out to it).

| Agent | Role | Tools | Owns |
|:------|:-----|:------|:-----|
| **Ghost** | General-purpose precision operative — executes one well-scoped task or brief end to end, including implementing a change's tasks | `read grep glob write code shell` | all six OpenSpec operations |
| **Spectre** | Planning operative — drives the front half of a change: investigates, scaffolds proposals, revises plans as understanding evolves | `read grep glob write code shell` | `openspec-explore`, `openspec-propose`, `openspec-update-change` |
| **Banshee** | Independent review/fix operative — a second pair of eyes across a wider field than Ghost's single task; finds bugs, runs tests, traces to root | `read grep glob write code shell` | `openspec-explore`, `openspec-propose`, `openspec-update-change`, `openspec-apply-change` |
| **Wraith** | Recon and documentation operative — research, investigation, writing project docs; read-only over code | `read grep glob shell` | none (adjacent — reads change context, doesn't edit it) |
| **Reaper** | Cleanup operative — closes out finished changes | `read grep glob write shell` | `openspec-sync-specs`, `openspec-archive-change` |
| **Raven** | Watcher and messenger — skims all crew mailboxes, checks task state, and carries messages between personas and the Admiral. Dispatches bounded next steps without implementing work. Captain-loop behaviour is injected via standing order template, not baked into the persona. | `read grep glob shell` | dispatch via the `kirocrew` CLI and the crew gateway's REST API |

The five worker personas form the OpenSpec cycle: Spectre explores and
proposes, Ghost implements, Banshee independently reviews and fixes, Reaper
syncs specs and archives the change, and Wraith researches and documents what
the cycle surfaces. Raven is separate from that cycle: the Captain is the
recurring check-in loop itself, not Raven — Raven is only the persona that
loop dispatches each cycle to watch the crew and carry its messages. Not
every task needs the full worker loop; small, self-contained work can start
and end with a single Ghost.

### Opt-in Captain path

The fully manual relay remains available: an Admiral can dispatch and pick up
each persona task directly. Captain has one autonomous mechanism per crew: a
recurring `/api/crons` job named `captain` that dispatches Raven in a
persistent session.

- **Free-form standing order:** call `captain(crew_id, action="order",
  message="<standing order>", interval=<n>)` or provide a cron expression.
- **Built-in SDD template:** call `captain(crew_id, action="order",
  template="sdd", change_name="<change>", interval=<n>)`. The template
  directs Raven to read the named change's real OpenSpec status and `tasks.md`
  state on every check-in, dispatch Spectre for incomplete planning, Ghost for
  unchecked implementation tasks, Banshee for an independent review, and Reaper
  to sync specs and archive after a clean review. After one fix-and-re-review
  cycle with unresolved findings, Raven escalates to the Admiral instead of
  looping; it confirms archival from OpenSpec state rather than memory.

Both forms append the resolved order to `captain@localhost` and use the same
Raven check-in. `captain(..., action="status")` reports the job's enabled state,
last-run summary, and both Captain and Admiral mailbox counts; `action="stop"` pauses the cron
with its history and mailbox intact. A scheduled check-in has a `job_id`, not a
dispatch `task_id`, so `steer` is not its control channel. The
`transport://orders` resource lists each built-in template's name, description,
and full body before an Admiral orders it or adapts it into a message.

Ghost and Banshee carry the same tool grant — the difference is role, not
permission: Ghost stays inside a given brief, Banshee is the independent pass
that goes looking for what's wrong across the whole thing. Ghost is the one
agent with the full OpenSpec lifecycle available to it — explore through
archive — on the logic that a well-scoped task should be drivable end to end
without a hand-off. Banshee gets explore through apply for whatever it finds,
but not sync-specs or archive-change: an independent reviewer still hands a
fix off to Reaper to formally close out, rather than closing its own findings
on its own authority — that keeps fixing and the formal record of closing as
two separate checkpoints, even when Banshee drives the fix itself. Banshee's
preferred pattern is still to amend the existing change
(`openspec-update-change`) when the fix fits, or propose a new one
(`openspec-propose`) when it doesn't, rather than patching code ad hoc.

## Steering, not enforcement

The `tools`/`allowedTools` arrays in each agent JSON are a real technical
gate — KiroCrew enforces those. The "owns" column above is not: skills are
copied crew-wide (every crew gets all `openspec-*` skills, not a subset per
agent), and a custom agent inherits every default resource — including every
skill — unless both `chat.disableInheritingDefaultResources` is set *and* the
agent defines its own `resources` list. None of the six currently do, so any
agent can technically invoke any `openspec-*` skill regardless of what its
prompt says it "owns". The division above is enforced only by each agent's
own system prompt — it tells the model what it's meant to focus on, it
doesn't block the alternative. Raven's five-worker roster is likewise
prompt-level guidance: a dispatched KiroCrew session has no native MCP
surface for subagent control, so Raven dispatches, steers, and continues
worker tasks over the crew gateway's own REST API (with the CLI covering
routine listing and its own cron pause/resume) — nothing in that call path
technically restricts the `agent` value Raven names; transport's allowlist
still enforces all six names for `dispatch` and `schedule`.

Two related things are deliberately not built yet: per-agent skill scoping
via `resources`/`skill://` (which would make the "owns" column a real
technical boundary), and per-crew workspace seeding/customization. Revisit
if role bleed between agents becomes a real problem in practice.
