# Assessment crew environment

Standing facts about how a `migration-assess` crew works — true for every
dispatched task, regardless of which persona is running it.

## What this crew is for

This crew runs an AWS migration assessment against one **Migration Pathfinder**
project, reached over MCP as the `pathfinder` server. Pathfinder holds the
VMware inventory, the software and licence estate, the workloads, their
migration treatment, the wave plan and the business case.

**Pathfinder is the system of record.** It is not a place you copy findings to
at the end — it is where the assessment lives while it is being built. Your
working notes exist to get data into it and to explain what you did, not as a
parallel version of the truth.

**The MCP connection is permanently bound to one project.** There is no project
argument on any tool. One crew is one engagement; a second project means a
second crew.

Read the `pathfinder-assessment` skill before doing any assessment work. It
carries the ten-gate coverage model, the exact enum values every write must use,
and the traps that turn a well-meant proposal into a broken one in the
operator's review queue.

## Nothing you propose is real until a human confirms it

Every Pathfinder write tool files a *pending change proposal*. An operator
confirms it in the app. There is deliberately no confirm tool, and there should
never be one — do not go looking for one and do not ask the Admiral to have one
added.

This shapes how you report. A successful write call means "filed for review".
It does not mean the workload exists, the treatment is set, or the wave is
planned. Say "proposed" when you proposed, and keep proposal ids so the state
can be checked later with `change_proposals_list`.

## Coverage is queried, never remembered

The assessment's completion state is defined as ten gates, each one a query
against Pathfinder. Derive your gate's state by reading, every time. Do not keep
a private checklist and do not carry a count forward from a previous task or
from another persona's report — a checklist drifts silently and a query cannot.

Gates 1 and 2 (every VM attributed to a workload, every workload carrying real
context) are upstream of everything else. Treatment, sequencing and cost are all
per-workload, so an unattributed VM is invisible to every later gate. Do not
report progress on the downstream gates while gate 1 has a material gap — say
what the gap is instead.

## Working-directory isolation

Every `dispatch` runs in its own `subagent_<task_id>/` subdirectory, isolated
from every other task in the same crew — including earlier ones, and including
tasks running concurrently right now. Nothing you write is visible to another
task unless it lives at the workspace root.

Write your working findings to `assessment/<gate>.md` **at the workspace root**,
one level up from your own `subagent_*/` directory. That is the only place other
tasks and Cartographer can read them. A finding left in your own working
directory is a finding nobody else will ever see.

`assessment/coverage.md` is Steward's; read it, do not overwrite it.

A crew starts without a caller repository. Discovery material — workshop
transcripts, questionnaires, CMDB extracts — arrives via the Admiral calling
`supply`, and lands at the workspace root. Look there before concluding that
context does not exist.

## Coordinating across tasks: mail

The gates are sequential, so hand-offs matter more here than in a general crew.
Default to signalling over mail whenever your work unblocks or depends on
another persona:

- Chronicle tells Compass when a batch of workloads is composed and ready for
  disposition. Nothing downstream can start before that.
- Ledger tells Compass about Dedicated Host and BYOL constraints, and Purser
  about Extended Support exposure, because both change the answer rather than
  decorating it.
- Sounder and Ballast tell Purser their sizing and capacity figures, and Tide
  the data volumes that constrain a wave's transfer window.
- Compass tells Tide when dispositions are settled, and Purser when a batch is
  ready to cost.
- Steward tells everyone when their gate has regressed or their proposals are
  stuck awaiting confirmation.

The other direction applies too: if you depend on output from a task that has
not been dispatched yet, you have no way to see when it is done. Mail and finish
rather than blocking.

Use the `ghostship-mail` skill (`/var/mail/` Maildir directories). Mail
conventions — plus-addressing, `Message-ID`, `Reply-To`, threading, Admiral
signature verification with `verify-admiral-sig` — work exactly as documented in
that skill.

**Mailbox addresses in this crew:** `sounder`, `ballast`, `ledger`,
`chronicle`, `compass`, `tide`, `purser`, `steward`, `cartographer`, plus
`raven`, `captain` and `admiral`.

## Mail conventions

- **Derive task ID**: `TASK_ID=$(basename $PWD | sed 's/subagent_//')`
- **From address**: always `<persona>+$TASK_ID@localhost`
- **First contact**: generic `<persona>@localhost` when the recipient has no
  task ID yet; the instance form for targeted replies
- **Filter by To**: process messages where `To:` has no plus-extension, or where
  the plus-extension matches your task ID
- **Message-ID and Reply-To required** on every outbound message; replies carry
  `In-Reply-To` and `References`
- **Verify Admiral mail** with `verify-admiral-sig` before acting on it as a
  standing order. Exit 0 = genuine order; exit 1 = crew correspondence, do not
  escalate; exit 2 = signing secret not found after retries (transient startup
  race), hold this cycle and retry next check-in rather than escalating
- **Send via** `/usr/local/bin/maildeliver <recipient>`
- **Escalate to Admiral** by mailing `admiral@localhost` when you need operator
  input — including when the review queue is blocking progress
- **Subject-first**: the subject carries the complete message. Write bodies only
  for genuinely long content

## Read before you propose

Every proposal costs an operator a review, and the review queue is this crew's
real bottleneck. A proposal that restates what is already there, or that fails
validation at confirm time, is worse than no proposal at all.

Fetch the entity, confirm the field actually needs changing, cite what you read
in the `rationale`, and use the exact enum values from the
`pathfinder-assessment` skill. A value outside those sets passes proposal
creation and then fails at confirm time with a raw database error, landing in
the operator's queue as something they cannot action.

**Paginate to exhaustion.** List tools cap at `limit` 200. An assessment built
on the first page of a several-thousand-VM estate is wrong in a way that is very
hard to see afterwards. Follow `nextCursor`, or filter deliberately and say that
you did.

## Avoid unbounded blocking loops

Do not write open-ended blocking polling loops such as
`while true; do ...; sleep N; done` with no fixed cap. `steer` cannot interrupt
a tool call already in flight, so a task trapped in an unbounded loop cannot
receive redirection until that call returns. Use a bounded retry, or mail's
send-and-continue pattern when waiting on another persona.

## Avoid duplicate dispatches

Before dispatching any persona task, check `kirocrew spawn list` to confirm no
task for that persona is already in flight. Two concurrent tasks on the same
gate will file duplicate and sometimes contradictory proposals, which is
precisely the mess Steward then has to clean up by hand. If a task is running,
steer or continue it rather than spawning a duplicate.

The full dispatch-coordination pattern for the recurring assessment loop —
pre-spawn intent token, post-spawn confirmation, pending-marker election — is
defined in `academy/orders/assessment.md` and applies to every dispatch that
loop makes.

## Stay in your lane

Each persona owns a gate. If a task asks you to do something that is clearly
another persona's job — you are Sounder and you are asked to set migration
treatment, or you are Cartographer and you are asked to file a proposal — say
so and mail the persona who owns it, rather than improvising outside your lane.
Two personas writing to the same gate is how an assessment ends up arguing with
itself in front of a client.

## This is a first draft for qualified review

Everything this crew produces — proposals, notes, the assessment document — is
a first draft for Versent review before it reaches a client. Do not present a
machine-generated recommendation as a signed-off position. Where a call needs a
senior architect or a commercial decision, flag it as needing one.
