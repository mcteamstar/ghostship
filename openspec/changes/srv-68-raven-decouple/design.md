# Design — srv-68-raven-decouple

## Context

See proposal.md — Why.

Three files carry Raven's Captain-loop behaviour today:

1. **`academy/agents/raven.json`** — the persona prompt, which contains `_RAVEN_SELF_CANCEL`, `_RAVEN_STORE_RESOLUTION`, and the "standing orders only change via Admiral mail" contract baked in.
2. **`transport/server.py`** — the `_RAVEN_SELF_CANCEL`, `_RAVEN_STORE_RESOLUTION`, `_RAVEN_MAILBOX_SKIM`, and `_RAVEN_GATEWAY_ORIENTATION` constants used to compose both the `sdd` Captain template and the base `raven.json` prompt (the file is generated from these constants at startup via `_patch_crew_config`/`_copy_agents`).
3. **`academy/skills/radio/SKILL.md`** — the inter-agent messaging skill, currently named "radio".

## Goals

- Raven's `raven.json` describes only what a Raven always does, regardless of whether it's in a Captain loop or dispatched directly.
- The `sdd` Captain template gains all the Captain-loop-specific paragraphs explicitly.
- The `radio` skill and `radio-messaging` spec become `mail`.
- Mail usage conventions are documented in `STANDING_ORDERS.md` and the renamed skill.

## Non-Goals

- Changing how mail is delivered (the `radio-unix-mail` stub's MTA idea is out of scope).
- Changing the mbox format or the `_write_captain_mail` transport implementation.
- Per-persona system users.

## Approach

### 1. Raven prompt rewrite

The `raven.json` prompt is authored directly in `academy/agents/raven.json` — `_copy_agents` copies it verbatim into the crew, it is not rendered from `server.py` constants. The constants `_RAVEN_SELF_CANCEL`, `_RAVEN_STORE_RESOLUTION`, `_RAVEN_MAILBOX_SKIM`, and `_RAVEN_GATEWAY_ORIENTATION` in `server.py` are used only to compose the Captain template strings — not injected into `raven.json` at runtime.

New `raven.json` prompt structure:
```
You are a Raven. Ravens watch and carry messages.

Each task, read the full picture: skim all mailboxes (/var/mail/ghost,
/var/mail/spectre, /var/mail/banshee, /var/mail/wraith, /var/mail/reaper,
/var/mail/admiral) and check crew task state. Reading mailboxes never
marks anything as read.

Write mail to any address when you need to carry a message or report.
[gateway orientation — CLI for routine ops, REST for the 4 gaps]
[.local_secret auth guidance]

Don't implement, review, sync specs, or archive. Don't edit files.
Hold or report when nothing to act on.
```

### 2. Captain template gains Captain-loop paragraphs

The `sdd` and free-text Captain templates in `server.py` already interpolate `_RAVEN_*` constants. After the rewrite, the templates gain the self-cancel and store-resolution paragraphs explicitly (currently these also appear in the raven.json prompt — after this change they only appear in the template).

The `_RAVEN_SELF_CANCEL` and `_RAVEN_STORE_RESOLUTION` constants stay in `server.py` for reuse in the templates. `_RAVEN_MAILBOX_SKIM` is removed (its content moves into the lean raven.json prompt directly, since mailbox skimming is generic Raven behaviour). `_RAVEN_GATEWAY_ORIENTATION` stays in server.py and continues to be injected into the templates (keeping a single source of truth for the REST API auth guidance, which also appears in raven.json).

### 3. Mail rename

| Old | New |
|:----|:----|
| `academy/skills/radio/` | `academy/skills/mail/` |
| `academy/skills/radio/SKILL.md` skill name `radio` | skill name `mail` |
| `openspec/specs/radio-messaging/` | referenced as `mail` in delta; physical rename on archive |
| All `radio` references in STANDING_ORDERS, agent prompts, docs | `mail` |

The `radio-unix-mail` change stub is superseded by this change for the naming portion. Leave it open for the MTA work if that's ever picked up, but note it in the stub.

### 4. Mail conventions in STANDING_ORDERS

Add a "Mail" section to `STANDING_ORDERS.md` covering:
- Derive your task ID from `$PWD`: `TASK_ID=$(basename $PWD | sed 's/subagent_//')`
- Always use `<persona>+$TASK_ID@localhost` as your `From:` address
- Generic `<persona>@localhost` for first contact; instance form for replies
- Filter your mailbox by `To:` — only process messages addressed to your instance (no plus-extension, or plus-extension matching your task ID)
- Mail Admiral at `admiral@localhost` when you need operator input
- Reading a mailbox never modifies it
- **Subject-first**: put the complete message in the subject. Body only for content too long to fit — diffs, task lists, error logs. A one-liner status, a handoff notification, a request: subject only, empty body.

Same conventions go in the renamed `ghostship-mail` skill's `SKILL.md`. Update the send examples to show subject-only messages (empty body).

### 5. `pickup` full mail skimming

File: `transport/server.py`

Always read all 8 mailboxes on every `pickup` call (`/var/mail/ghost`, `/var/mail/spectre`, `/var/mail/banshee`, `/var/mail/wraith`, `/var/mail/reaper`, `/var/mail/raven`, `/var/mail/captain`, `/var/mail/admiral`). These are flat files, a few KB each — reading all is cheaper than selectively reading some.

Report selectively based on how `pickup` was called:

- **Task-specific** (`task_id` given): return `<agent>_mail`, `<agent>_subjects`, `captain_mail`, `captain_subjects`, `admiral_mail`, `admiral_subjects`
- **Crew-wide** (no `task_id`): return all six persona counts + subjects, plus captain and admiral

Parse `Subject:` headers from unread messages. Bodies are not read. Reading never modifies any mailbox file.

## Files Changed

- `academy/agents/raven.json` — prompt rewrite
- `academy/skills/radio/` → `academy/skills/ghostship-mail/` (git mv)
- `academy/steering/STANDING_ORDERS.md` — radio → mail, add conventions including subject-first
- `transport/server.py` — remove `_RAVEN_MAILBOX_SKIM`, keep other constants, update Captain templates, extend `_read_admiral_mail` to return subject lines
- `docs/agents.md` — update Raven description, radio → mail
