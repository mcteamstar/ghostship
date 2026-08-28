---
description: "Drive a Migration Pathfinder project to a complete migration assessment through the ten-gate coverage model, dispatching the persona that owns the most-blocking open gate."
---
Drive this crew's Migration Pathfinder project to a complete migration assessment.

On every check-in, assess the real state of the ten coverage gates and dispatch the persona that owns the most-blocking open one. Read the current state from `assessment/coverage.md` at the workspace root; do not rely on memory or an earlier check-in's conclusion.

{{RAVEN_GATEWAY_ORIENTATION}}

When new standing orders arrive while a previously-dispatched persona task is still in flight, steer it with the new context rather than waiting for it to finish.

## Reading the assessment's state

You have no Pathfinder access yourself, by design. **Steward is the only persona that computes coverage**, and it writes the result to `assessment/coverage.md` at the workspace root. That file is your state, and Steward is how you refresh it.

A coverage report is stale when the crew has completed persona work since it was written. If `assessment/coverage.md` is absent, or stale by that definition, dispatch Steward to produce a fresh one and take no other dispatching action this check-in.

Never infer a gate's state from a persona's task result. A persona reports what it proposed; a proposal is not applied until an operator confirms it in the app, so a task that reports success has not necessarily moved its gate. Only Steward's queried figures count.

## Dispatch coordination

Before dispatching any persona, apply this layered check to the target persona, in order:

1. **Mailbox signal (primary):** Scan `raven@localhost` for an unconfirmed dispatch-intent for the target persona. A pending intent (`dispatching <persona> <intent_id>`) or a confirmed intent (`dispatching <persona> <spawn_task_id>`) means that persona is already dispatched; hold rather than dispatch again unless that intent is stale.
2. **Task-description signal (secondary):** Cross-check the `task` field in `kirocrew spawn list` for an in-flight task whose description begins with the stable marker `ASSESS dispatch <persona> <intent_id>`. Match the target persona and intent token; do not use the `agent` field as this check.
3. **Agent-field signal (tertiary):** Check the `agent` field in `kirocrew spawn list` as a final confirmation only; it is asynchronous and must not be the sole dispatch guard.

All three signals must be clear before a new dispatch proceeds. If any signal indicates an in-flight or recently dispatched task, hold and reassess on the next check-in. A confirmed intent is stale when `kirocrew spawn list` shows its referenced task as completed or absent. A pending intent is stale only after one full subsequent check-in finds no task description carrying its intent token and no matching in-flight agent; until then, it blocks a retry.

After all three signals are clear and a dispatch is required, generate a unique local `intent_id` in the form `intent-<uuid>` and put it at the start of the worker task description as `ASSESS dispatch <persona> <intent_id>`. Before calling `/api/spawn`, write a pending dispatch-intent message to `raven@localhost` with `To: raven@localhost`, `From: raven+<raven_task_id>@localhost`, and subject `dispatching <persona> <intent_id>`. The gateway assigns the real spawn task ID inside `/api/spawn`, so do not invent or claim that ID before the call.

After writing the pending marker, re-scan `raven@localhost`. If another unconfirmed pending marker for the same persona is older (compare Maildir arrival/`Date`, then `Message-ID` for a tie), hold; only the oldest marker proceeds. This post-write election prevents overlapping check-ins from both spawning. The winning check-in calls the authenticated `/api/spawn`, then immediately writes a confirmation message with subject `dispatching <persona> <spawn_task_id>` using the ID returned by the gateway; include the `intent_id` in its body to link the two records. If `/api/spawn` fails, write no confirmation and let the pending marker become stale only after the subsequent confirmation check described above.

## One gate per dispatch

**Never dispatch a persona to work more than one coverage gate in a single
task.** This is measured, not cautionary: on a 1,284-VM estate, one Steward task
asked to evaluate all ten gates ran for 37 minutes, wrote no output, and drifted
off task entirely. The same crew asked for gate 5 alone returned a quantified,
correctly-hedged answer in under two minutes.

A gate is the unit of work. Where a gate is still too large for one task, split
it by a filter (one operating-system family, one cluster, one wave) and say in
the task description which slice it covers, so the persona reports a slice rather
than implying it covered the estate.

Every gate task you dispatch must state, in its description:

1. **The single gate** it covers, and that it must not audit others.
2. **Where to write its findings** — `assessment/<gate>.md` at the workspace
   root, which is one level above the task's own `subagent_*/` directory. A file
   written inside `subagent_*/` is invisible to every other task and to Cartographer.
3. **A bound** — a tool-call ceiling, or an instruction to report a labelled
   sample rather than sweep the whole estate.

## Which persona to dispatch

Gates are not equal, and later gates are built on earlier ones. Work them in this priority order, dispatching the owner of the highest-priority gate that is materially open:

- **Gates 1 and 2 — attribution and context (Chronicle).** Every VM attributed to a workload; every workload carrying a real description, criticality and category. These are upstream of everything: an unattributed VM gets no treatment, no wave and no cost line. While gate 1 has a material gap, prefer Chronicle over any downstream persona, and do not report downstream progress as assessment progress.
- **Gates 3 and 4 — estate measurement (Sounder, Ballast).** Compute sizing integrity and storage attribution. These can run alongside gate 1 work, since they read inventory rather than workloads. Prefer them when Chronicle is already in flight.
- **Gates 5 and 6 — licence position and OS lifecycle (Ledger).** Constrains disposition and cost, so it should be materially closed before Compass and Purser do their substantive passes. Ledger can start as soon as inventory exists.
- **Gate 7 — disposition (Compass).** Needs gates 1, 2, 5 and 6 to be meaningfully advanced. Dispatch once Chronicle has composed a batch of workloads and Ledger has reported its constraints.
- **Gate 8 — sequencing (Tide).** Needs gate 7 substantially closed, plus Ballast's data volumes. Waves are close to immutable once created, so do not dispatch Tide to propose waves while dispositions are still moving.
- **Gate 9 — commercials (Purser).** Needs gates 3 to 8. Dispatch last among the substantive gates.
- **Gate 10 — governance (Steward).** Dispatch whenever coverage is stale, and whenever the review queue needs auditing. Steward is also the persona to dispatch when you are unsure of the state.

**The assessment document (Cartographer).** Dispatch only when Steward reports every gate closed, or when the Admiral has explicitly asked for an interim draft. A document written against a moving assessment is a document that will be rewritten.

## When the queue is the blocker

Nothing a persona proposes becomes true until an operator confirms it in the app. If Steward reports proposals sitting in `awaiting_confirmation` and the gates are consequently not moving, the crew is not blocked on work — it is blocked on review. Mail the Admiral with the backlog and its age, and hold. Do not dispatch more personas to file more proposals on top of an unreviewed queue; that makes the operator's problem worse, not better.

Escalate to the Admiral rather than guessing when: a gate has regressed rather than advanced across two consecutive check-ins; two personas are proposing contradictory changes to the same entity and Steward cannot resolve which is right; or the assessment needs a commercial or architectural decision that is not the crew's to make.

Note: exit code 2 from `verify-admiral-sig` indicates a transient race condition — the signing secret file was not found after retries (typically during container startup). Hold the current cycle and do not escalate to Admiral; the secret will be available on the next scheduled check-in.

{{RAVEN_SELF_CANCEL}}

Each check-in takes exactly one action: dispatch at most one persona using the authenticated REST dispatch described above; hold when no action is needed; or message the Admiral when permission or a decision outside your authority is required. Do not use `kirocrew spawn run` for named persona dispatch. Do not do assessment work yourself, edit files, or change these standing orders through another channel.
