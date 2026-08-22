# Tasks — srv-68-raven-decouple

## Task 1 — Rewrite `raven.json` prompt

File: `academy/agents/raven.json`

Rewrite the `prompt` field to be a lean "You are a Raven" persona definition:
- Opens with "You are a Raven. Ravens watch and carry messages."
- Covers generic behaviour: skim all mailboxes each task (ghost, spectre, banshee, wraith, reaper, admiral), check crew task state via `spawn list`
- Covers mail writing: write to any address when carrying a message or reporting
- Retains gateway orientation: kirocrew CLI for routine ops; REST + `.local_secret` for the 4 gaps (dispatch named persona, per-task detail, steer running task, continue finished task)
- Retains auth guidance for `.local_secret` / `X-Internal-Secret`
- Ends with: don't implement, don't edit files, hold or report when nothing to act on
- Removes: self-cancel instruction, "standing orders only change via Admiral mail", OpenSpec store resolution, any implication Raven owns the cron job it runs inside

Update `welcomeMessage` to reflect the lean persona (remove Captain-specific framing).

## Task 2 — Fix `_format_captain_mail` subject and document source convention

File: `transport/server.py`

- Change the hardcoded `Subject: Standing order` to use the first line of the order body, truncated to ~72 chars, as the subject. Full body stays in the message body unchanged.
- Add a comment documenting the source convention: `From: admiral@localhost` is the only authorised source of standing orders; persona messages in the captain mailbox are crew correspondence.
- Update `_CAPTAIN_CHECKIN_TASK` to instruct Raven to distinguish `From: admiral@localhost` (standing orders) from `From: <persona>` (crew correspondence) when reading `/var/mail/captain`.

## Task 3 — Update Captain templates in `server.py`

File: `transport/server.py`

- Remove `_RAVEN_MAILBOX_SKIM` constant — its content is now in `raven.json` directly
- Keep `_RAVEN_SELF_CANCEL`, `_RAVEN_STORE_RESOLUTION`, `_RAVEN_GATEWAY_ORIENTATION`
- Update the `sdd` Captain template to explicitly include `_RAVEN_SELF_CANCEL` and `_RAVEN_STORE_RESOLUTION` paragraphs (they were previously duplicated in both raven.json and the template — now they live only in the template)
- Update the free-text Captain template similarly
- Verify the assembled template still reads coherently end-to-end

## Task 3 — Rename `radio` skill to `mail`

- `git mv academy/skills/radio academy/skills/mail`
- Update `SKILL.md` frontmatter: `name: radio` → `name: mail`, `description` updated to drop "radio" framing
- Update all references to the skill name within `SKILL.md` itself
- Verify no other files reference `academy/skills/radio` (grep for `skills/radio`)

## Task 4 — Add mail conventions to `STANDING_ORDERS.md`

File: `academy/steering/STANDING_ORDERS.md`

- Rename any section or reference from "radio" / "Radio" to "Mail"
- Add a "Mail conventions" section covering:
  - Derive task ID: `TASK_ID=$(basename $PWD | sed 's/subagent_//')`
  - Use `<persona>+$TASK_ID@localhost` as `From:` address
  - Generic `<persona>@localhost` for first contact; instance form for targeted replies
  - Filter mailbox by `To:` — only process messages with no plus-extension or matching your task ID
  - Mail `admiral@localhost` when you need operator input
  - Reading mailboxes never modifies them
  - **Subject-first**: the subject carries the complete message. Read subject lines first when checking any mailbox — they tell you what's there without opening bodies. Only open a body when the subject alone isn't sufficient to understand what action is needed. Write bodies only for genuinely long content (diffs, task lists, error logs).
  - **Captain mailbox source convention**: `From: admiral@localhost` in `/var/mail/captain` = standing orders. `From: <persona>` = crew correspondence. Never conflate the two — a persona cannot issue standing orders by mailing captain.

## Task 5 — Update renamed `ghostship-mail` skill with same conventions

File: `academy/skills/ghostship-mail/SKILL.md`

- Update skill name in frontmatter: `name: ghostship-mail`
- Update description to drop "radio" framing
- Add subject-first convention to the "Sending Mail" section — show an example with empty body
- Update the send helper examples to demonstrate subject-only messages
- Add a "Reading Mail" note: read subject lines first; open body only if needed

## Task 6 — Extend `pickup` to skim all relevant mailboxes

File: `transport/server.py`

Extend the `pickup` implementation to skim subject lines from mailboxes on every call:

- **Task-specific pickup** (`task_id` given): read `/var/mail/<agent>` for the agent that ran the task, plus always `/var/mail/captain` and `/var/mail/admiral`
- **Crew-wide pickup** (no `task_id`): read all six persona mailboxes (`/var/mail/ghost`, `/var/mail/spectre`, `/var/mail/banshee`, `/var/mail/wraith`, `/var/mail/reaper`, `/var/mail/raven`), plus `/var/mail/captain` and `/var/mail/admiral`

For each mailbox: parse `Subject:` headers from unread mbox messages. Return `<name>_mail: N` (count) and `<name>_subjects: [...]` (subject lines) for each. Reading never modifies any mailbox file. Bodies are not read.

Write tests:
- Task-specific pickup returns agent + captain + admiral subjects
- Crew-wide pickup returns all persona + captain + admiral subjects
- Empty mailboxes contribute zero counts and empty subject lists

## Task 7 — Update `docs/agents.md`

File: `docs/agents.md`

- Update Raven's description to reflect the lean persona (watcher and messenger, not Captain-loop-specific)
- Replace any "radio" references with "mail" / "ghostship-mail"
- Note that Captain-loop behaviour is injected via standing order, not baked into Raven

## Task 8 — Run tests and verify

- `python3 -m py_compile transport/server.py && echo OK`
- `python3 -m unittest discover -s transport -p "test_*.py"` — all tests pass including new pickup subjects test
- Verify `academy/skills/ghostship-mail/SKILL.md` exists and `academy/skills/radio/` is gone
- Grep for stale `radio` references: `grep -r "radio" academy/ docs/ openspec/specs/ --include="*.md" | grep -v archive`
- Spot-check assembled Captain template still contains self-cancel and store-resolution paragraphs
