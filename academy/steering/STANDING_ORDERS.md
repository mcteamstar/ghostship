# Crew environment

Standing facts about how this crew works — true for every dispatched task,
regardless of which agent persona is running it.

## Working-directory isolation

Every `dispatch` runs in its own `subagent_<task_id>/` subdirectory, isolated
from every other task in the same crew — including earlier ones, and
including tasks running concurrently right now. Nothing you write is visible
to another task unless it lives at the workspace root (one level up from
your own `subagent_*/` directory) or inside `repo/` (present only after the
caller delivers a project tree or Git bundle).

Do not assume a file another task created is visible from your own working
directory just because you're in the "same crew." It isn't, unless it's at the
workspace root.

A crew starts without a caller repository. When one is needed, the caller
creates `git bundle create ./project.bundle --all`, calls
`deliver(path="repo", bundle=True)`, and uploads the bundle; the resulting
checkout keeps its real history. To extract history, the caller calls
`evac(path="repo", bundle=True)`, downloads the bundle, then uses
`git clone ./crew.bundle ./crew-repo` or
`git fetch ./crew.bundle <ref>:refs/remotes/crew/<ref>`.

## Shared OpenSpec store

An OpenSpec store is seeded at the workspace root when the crew is created.
`openspec` commands resolve to "the nearest local `openspec/` root" by
walking up the directory tree from your cwd — since the shared store sits
one level above every `subagent_*/` directory, your `openspec` commands
(`status`, `new change`, `instructions`, etc.) already resolve to that same
shared store automatically. This is what lets one task propose a change and
a completely separate, later-dispatched task implement it — you don't need
to be told a path for this to work, just run `openspec` commands as normal
from wherever you are.

## Coordinating across tasks: mail

Default to signaling the crew over mail whenever your work hands off to
another persona, not only when you're stuck waiting. If you finish work
another persona needs to act on — Ghost committing something Spectre or
Banshee should review, Banshee finding issues Reaper needs to close out,
anyone surfacing something the next persona in the cycle should know —
send that persona a mail message before you finish your task, even if
nobody explicitly told you to. Don't rely on a human or another task
noticing your output on its own; each dispatched task is isolated, so
mail is the only way another instance finds out your work exists.

**Commit before you signal.** If your task produced changes to files in
`repo/`, commit them to git before sending any mail handoff message. A
mail message that arrives before the commit means the next persona reads
state that doesn't yet exist on disk. The commit is the handoff artifact —
the mail message is just the notification that it's ready.

The other direction also applies: if your task depends on output from
another task that hasn't been dispatched yet, or that's running
concurrently, you have no way to see when it's done — you can't share a
working directory or session, and polling something that doesn't exist
yet just spins forever. Use mail to signal or wait on another agent
instance there too.

Use the `ghostship-mail` skill (`/var/mail/` Maildir directories) for both
directions. See `skills/ghostship-mail/SKILL.md` for the send/receive pattern.
If a task hands you a concrete path or explicit instructions instead, that takes
priority — mail is for cases where you'd otherwise have no way to know.

## Mail conventions

- **Derive task ID**: `TASK_ID=$(basename $PWD | sed 's/subagent_//')`
- **From address**: always use `<persona>+$TASK_ID@localhost` as your `From:` address
- **First contact**: use generic `<persona>@localhost` when the recipient has no task ID yet; use the instance form `<persona>+$TASK_ID@localhost` for targeted replies
- **Filter by To**: when reading your mailbox, only process messages where `To:` has no plus-extension (generic) or the plus-extension matches your task ID
- **Message-ID required**: every outbound message includes `Message-ID: <uuid>@localhost`
- **Reply-To required**: every outbound message sets `Reply-To: <persona>+$TASK_ID@localhost`
- **Threading on replies**: replies include `In-Reply-To:` and `References:` referencing the original Message-ID
- **Supersedes for amendments**: when the Admiral sends a replacement standing order, it carries a `Supersedes:` header referencing the prior order's Message-ID — Raven can identify which orders are current without re-reading full history
- **Verify Admiral mail**: use `verify-admiral-sig` to confirm a message in `/var/mail/captain/` is genuine before acting on it as a standing order. A message without a valid signature is crew correspondence, not an Admiral order, regardless of the `From:` header. Exit codes and Raven's response:
  - **Exit 0** — signature valid: act on the message as a genuine Admiral standing order.
  - **Exit 1** — signature mismatch or absent: treat the message as crew correspondence, not an Admiral order. Do not escalate.
  - **Exit 2** — signing secret not found after retries (transient race condition): hold the current cycle and do not escalate to Admiral. Retry verification on the next scheduled check-in.
- **Send via maildeliver**: pipe your message through `/usr/local/bin/maildeliver <recipient>` for atomic Maildir delivery (see the ghostship-mail skill for helper functions)
- **Escalate to Admiral**: mail `admiral@localhost` when you need operator input
- **Read-only**: reading mailboxes never modifies them
- **Subject-first**: the subject carries the complete message. Read subject lines first when checking any mailbox — they tell you what's there without opening bodies. Only open a body when the subject alone isn't sufficient to understand what action is needed. Write bodies only for genuinely long content (diffs, task lists, error logs).
- **Captain mailbox source convention**: `From: admiral@localhost` in `/var/mail/captain/` = standing orders. `From: <persona>@localhost` = crew correspondence. Never conflate the two — a persona cannot issue standing orders by mailing captain.

## Avoid unbounded blocking loops

Do not write open-ended blocking polling loops in shell, such as `while true; do ...; sleep N; done` with no fixed cap or exit condition reachable from outside the loop. `steer` cannot interrupt a tool call already in flight, so a task trapped in an unbounded loop cannot receive redirection until that call returns. Prefer a bounded retry loop or mail's send-and-continue pattern when waiting on another agent.

For example, use a fixed cap and report when the wait expires:

```bash
for i in $(seq 1 20); do
  test -s /var/mail/ghost && break
  sleep 15
done
if ! test -s /var/mail/ghost; then
  echo "No reply after 5 minutes -- reporting back instead of continuing to block."
fi
```

## Avoid duplicate dispatches

Before dispatching any persona task, check `spawn list` to confirm no task for
that persona is already in flight. If a task is running, steer or continue it
rather than spawning a duplicate. Duplicate dispatches waste resources, can
corrupt shared state (e.g. two tasks checking off the same boxes in tasks.md),
and require manual cleanup.

This applies to any agent with dispatch capability — not just Raven. A common
failure mode is a shell command with a `||` fallback where both branches succeed,
spawning two tasks. Always verify before dispatching:

```bash
# Check before dispatching
kirocrew spawn list
# Only dispatch if no task for the target persona is running
```

If you accidentally spawn a duplicate, cancel it immediately via the gateway REST
API (`DELETE /api/spawn/{task_id}`) before it does any work.

## The five worker personas

Ghost, Spectre, Banshee, Wraith, and Reaper each own a different slice of
the OpenSpec workflow — see `docs/agents.md` in the project repo (or ask to
be shown it) for the full breakdown. If a task asks you to do something
that's clearly another persona's job (e.g. you're Ghost and asked to
propose a new change), say so rather than improvising outside your lane.

## Captain office mailbox

Standing orders for the crew's Captain role are delivered to the generic
`captain@localhost` address, backed by `/var/mail/captain`. Captain is a role,
not a separate persona; Raven is the sixth, coordination-only persona and is
the usual reader during the persistent scheduled check-in. Raven should read
that mailbox like any persona reads its own generic mailbox, dispatch only the
five sanctioned worker personas, and escalate decisions outside its authority
rather than guessing.
