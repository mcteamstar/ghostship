## Why

Two related problems: Raven's `raven.json` prompt bakes in Captain-loop-specific behaviour (self-cancellation, standing-order ownership, OpenSpec store resolution) making it unusable as a general-purpose watcher/messenger persona; and the inter-agent messaging system is named "radio" (`radio-messaging` spec, `radio` skill, `STANDING_ORDERS.md` references) — a codename from early development that doesn't communicate what it is. Both are corrected here: Raven becomes a lean general-purpose persona, the messaging capability is renamed to reflect what it actually is, and the conventions for how agents use mail are made explicit.

## What Changes

**Raven decoupling:**
- **Strip Captain-loop behaviour from `raven.json`** — remove self-cancel, standing-order ownership, OpenSpec store resolution, and cron-job-management framing from the persona definition.
- **Rewrite Raven's prompt as a lean persona** — "You are a Raven." Generic behaviour: read all mailboxes (including Admiral), write mail to any address, watch crew state, dispatch named personas via gateway REST, use kirocrew CLI for routine ops. Does not implement or edit files.
- **Move Captain-loop specifics into the `sdd` standing order template** — reading `/var/mail/captain`, self-cancel when done, order-change contract, sanctioned persona list, OpenSpec store resolution all injected at job creation, not baked into the persona.
- **Retain gateway REST / `.local_secret` guidance in `raven.json`** — scoped to the four things the CLI can't do (dispatch a named persona, per-task detail, steer, continue). Generic Raven capability, not Captain-loop-specific.

**Mail naming:**
- **Rename the `radio` skill to `ghostship-mail`** — `academy/skills/radio/` → `academy/skills/ghostship-mail/`, skill name `radio` → `ghostship-mail`. The `ghostship-` prefix makes it clear this is a ghostship-native skill.
- **Rename the `radio-messaging` spec capability to `mail`** — `openspec/specs/radio-messaging/` → `openspec/specs/mail/`.
- **Update all references** — `STANDING_ORDERS.md`, `docs/agents.md`, `docs/architecture.md`, any inline references in agent prompts, the `radio-unix-mail` change stub (rename or close it as subsumed).

**Mail conventions:**
- **Document how agents use mail** — add a conventions section to `STANDING_ORDERS.md` and the renamed skill: when to mail vs dispatch directly, how to address (generic vs instance form), how to check only messages addressed to your instance, the admiral mailbox convention, and the captain mailbox convention.
- **Subject-first convention** — the subject line SHALL carry the full message wherever possible. The body is reserved for genuinely long context that cannot fit in a subject (e.g. a full diff, a multi-step task list). A one-liner status, a handoff notification, a request for the next step — all go in the subject only, with an empty body.
- **Captain mailbox source convention** — `From: admiral@localhost` in `/var/mail/captain` is a standing order (written only by the transport). `From: <persona>@localhost` is crew correspondence. Raven and any other reader SHALL distinguish these by `From:` header — a persona cannot issue standing orders by mailing captain.
- **Fix standing order subject** — `_format_captain_mail` currently hardcodes `Subject: Standing order` on every message. Change it to use the first line of the order body as the subject, so Raven can distinguish orders by subject without parsing bodies.

**`pickup` mail skimming:**
- Always read all 8 mailboxes on every `pickup` call (flat files, negligible cost). Report selectively: task-specific pickup returns agent + captain + admiral subjects and counts; crew-wide pickup returns all personas + captain + admiral. Subject lines surface as `<name>_subjects: [...]` alongside existing `<name>_mail: N` counts.

## Capabilities

### New Capabilities
_(none)_

### Modified Capabilities
- `agent-personas`: Raven's requirement changes — lean generic watcher/messenger, Captain-loop behaviour injected via standing order template not persona definition.
- `radio-messaging` (rename to `mail`): capability renamed; subject-first convention, mail usage conventions, and `pickup` full mail skimming added as new requirements.
- `task-orchestration`: `pickup` response shape changes — adds per-mailbox subject line fields alongside existing mail counts.

## Impact

- `academy/agents/raven.json` — prompt rewrite
- `academy/skills/radio/` → `academy/skills/ghostship-mail/` — rename skill directory and name
- `academy/steering/STANDING_ORDERS.md` — radio → mail, add mail conventions including subject-first and captain source convention
- `transport/server.py` — `_RAVEN_MAILBOX_SKIM` removed; `_RAVEN_SELF_CANCEL`/`_RAVEN_STORE_RESOLUTION` stay for Captain templates; `_format_captain_mail` subject fix; Captain templates gain explicit loop paragraphs; `pickup` extended to skim all 8 mailboxes and return subject lines
- `openspec/specs/radio-messaging/` → referenced as `mail` in delta spec (physical rename on archive)
- `docs/agents.md` — update Raven description, radio → mail
- No MCP tool interface changes; no breaking changes for existing Captain check-ins
